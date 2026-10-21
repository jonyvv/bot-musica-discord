import asyncio
import sys

from fastapi.testclient import TestClient

from resolver.infrastructure.updater import _UPGRADE, _VERSION, YtDlpUpdater, run_command
from resolver.presentation.api import create_app


class FakeRunner:
    def __init__(self, versions, upgrade_code=0):
        self.versions = list(versions)
        self.upgrade_code = upgrade_code
        self.calls = []

    async def __call__(self, args):
        self.calls.append(list(args))
        if list(args) == _VERSION:
            return (0, self.versions.pop(0)) if self.versions else (1, "")
        return self.upgrade_code, "pip output"


def updater_with(runner, sleeps=None, interval=100):
    updated = []

    async def sleep(seconds):
        if sleeps is not None:
            sleeps.append(seconds)

    instance = YtDlpUpdater(interval, lambda: updated.append(True), runner, sleep)
    return instance, updated


async def test_reports_update_when_version_changes():
    updater, updated = updater_with(FakeRunner(["2026.1.1", "2026.2.2"]))

    assert await updater.check_once()
    assert updated == [True]


async def test_no_action_when_version_is_unchanged():
    updater, updated = updater_with(FakeRunner(["2026.1.1", "2026.1.1"]))

    assert not await updater.check_once()
    assert updated == []


async def test_failed_upgrade_is_not_an_update():
    updater, updated = updater_with(FakeRunner(["2026.1.1"], upgrade_code=1))

    assert not await updater.check_once()
    assert updated == []


async def test_unknown_version_is_not_an_update():
    updater, updated = updater_with(FakeRunner([]))

    assert not await updater.check_once()
    assert updated == []


async def test_upgrade_command_installs_for_user_only():
    runner = FakeRunner(["1", "1"])
    updater, _ = updater_with(runner)

    await updater.check_once()

    assert _UPGRADE in runner.calls
    assert "--user" in _UPGRADE


async def test_run_forever_waits_between_checks_and_stops_after_update():
    sleeps = []
    runner = FakeRunner(["1", "1", "1", "1", "1", "2"])
    updater, updated = updater_with(runner, sleeps, interval=3600)

    await updater.run_forever()

    assert sleeps == [3600, 3600]
    assert updated == [True]


def test_background_task_runs_during_app_lifetime_and_is_cancelled():
    state = {"started": False, "cancelled": False}

    async def background():
        state["started"] = True
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            state["cancelled"] = True
            raise

    with TestClient(create_app(object(), background=background)) as client:
        client.get("/health")
        assert state["started"]

    assert state["cancelled"]


async def test_run_command_returns_code_and_combined_output():
    code, output = await run_command([sys.executable, "-c", "print('hola')"])

    assert (code, output) == (0, "hola")


async def test_run_command_reports_failure_and_stderr():
    script = "import sys; print('boom', file=sys.stderr); sys.exit(3)"

    code, output = await run_command([sys.executable, "-c", script])

    assert code == 3
    assert "boom" in output
