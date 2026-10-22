import importlib
import re
from pathlib import Path

import pytest

REQUIREMENTS = Path(__file__).resolve().parents[1] / "services" / "bot" / "requirements.txt"
VOICE_PACKAGES = ["PyNaCl", "davey"]


def declared() -> dict[str, str]:
    packages = {}
    for line in REQUIREMENTS.read_text().splitlines():
        if match := re.match(r"^([A-Za-z0-9_.\-]+)\s*==\s*([^\s;]+)", line):
            packages[match[1].lower()] = match[2]
    return packages


@pytest.mark.parametrize("package", VOICE_PACKAGES)
def test_voice_packages_are_pinned_in_the_bot_requirements(package):
    assert package.lower() in declared(), (
        f"{package} falta en services/bot/requirements.txt: sin él la voz no funciona en Docker"
    )


@pytest.mark.parametrize("module", ["nacl", "davey"])
def test_voice_modules_are_importable(module):
    importlib.import_module(module)


def test_discord_py_reports_voice_support():
    from discord import voice_client

    assert voice_client.has_nacl


def test_requirements_do_not_use_the_voice_extra_which_would_cap_pynacl():
    text = REQUIREMENTS.read_text()

    assert "discord.py[" not in text
