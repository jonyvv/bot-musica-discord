import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOWS = sorted((ROOT / ".github" / "workflows").glob("*.yml"))
DOCKERFILES = sorted((ROOT / "services").glob("*/Dockerfile"))
PINNED_ACTION = re.compile(r"^[\w.\-/]+@[0-9a-f]{40}(\s+#.*)?$")
PINNED_IMAGE = re.compile(r"@sha256:[0-9a-f]{64}")


def uses_lines(path: Path):
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if match := re.search(r"uses:\s*(\S.*)$", line):
            yield number, match[1].strip()


def test_there_are_workflows_to_check():
    assert WORKFLOWS, "no se encontraron workflows"


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_every_github_action_is_pinned_to_a_commit_sha(workflow):
    unpinned = [
        f"{workflow.name}:{n} {ref}"
        for n, ref in uses_lines(workflow)
        if not ref.startswith("./") and not PINNED_ACTION.match(ref)
    ]

    assert not unpinned, f"Acciones sin fijar por SHA: {unpinned}"


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_workflows_declare_least_privilege_permissions(workflow):
    text = workflow.read_text(encoding="utf-8")

    assert re.search(r"^permissions:\s*\n\s+contents:\s*read", text, re.M), (
        f"{workflow.name} debe declarar permisos minimos a nivel de workflow"
    )


@pytest.mark.parametrize("workflow", WORKFLOWS, ids=lambda p: p.name)
def test_checkout_does_not_persist_credentials(workflow):
    text = workflow.read_text(encoding="utf-8")
    checkouts = len(re.findall(r"actions/checkout@", text))

    assert len(re.findall(r"persist-credentials:\s*false", text)) == checkouts


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=lambda p: p.parent.name)
def test_every_base_image_is_pinned_by_digest(dockerfile):
    sources = [
        line
        for line in dockerfile.read_text(encoding="utf-8").splitlines()
        if line.startswith("FROM ") or "--from=" in line
    ]
    external = [
        line for line in sources if "--from=" not in line or "/" in line.split("--from=")[1]
    ]

    assert external
    assert all(PINNED_IMAGE.search(line) for line in external), external


@pytest.mark.parametrize("dockerfile", DOCKERFILES, ids=lambda p: p.parent.name)
def test_containers_do_not_run_as_root(dockerfile):
    users = re.findall(r"^USER\s+(\S+)", dockerfile.read_text(encoding="utf-8"), re.M)

    assert users
    assert users[-1] not in {"root", "0"}


def test_dependabot_covers_every_ecosystem_in_use():
    text = (ROOT / ".github" / "dependabot.yml").read_text(encoding="utf-8")

    for ecosystem in ("pip", "docker", "github-actions"):
        assert f"package-ecosystem: {ecosystem}" in text


def test_compose_publishes_no_ports_and_uses_secret_files():
    text = (ROOT / "docker-compose.yml").read_text(encoding="utf-8")

    assert not re.search(r"^\s+ports:", text, re.M)
    assert "secrets:" in text
    assert "DISCORD_TOKEN:" not in text.replace("DISCORD_GUILD_ID", "")
