import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SKIPPED_DIRS = {".venv", ".git", "node_modules", "__pycache__", ".ruff_cache", ".pytest_cache"}
FORBIDDEN_NAMES = re.compile(
    r"(^|/)(\.env|id_rsa|id_ed25519|cookies?[^/]*\.txt|[^/]*\.pem|[^/]*\.key|secrets/[^/]+)$"
)
PATTERNS = {
    "token de Discord": re.compile(r"[A-Za-z0-9_-]{24,}\.[A-Za-z0-9_-]{6,7}\.[A-Za-z0-9_-]{27,}"),
    "token de GitHub": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{36,}|github_pat_[A-Za-z0-9_]{50,})"),
    "clave privada": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH |DSA |PGP )?PRIVATE KEY"),
    "clave de AWS": re.compile(r"\bAKIA[0-9A-Z]{16}\b"),
    "secreto asignado": re.compile(
        r"(?i)\b(?:DISCORD_TOKEN|RESOLVER_API_KEY|API_KEY|CLIENT_SECRET|PASSWORD)\s*[:=]\s*"
        r"['\"]?[A-Za-z0-9_\-./+=]{16,}"
    ),
}


def find_secrets(text: str) -> list[str]:
    return [label for label, pattern in PATTERNS.items() if pattern.search(text)]


def tracked_files() -> list[str]:
    try:
        output = subprocess.run(
            ["git", "ls-files"], cwd=ROOT, capture_output=True, text=True, check=True
        ).stdout
        return [line for line in output.splitlines() if line]
    except (OSError, subprocess.CalledProcessError):
        return [
            str(p.relative_to(ROOT)).replace("\\", "/")
            for p in ROOT.rglob("*")
            if p.is_file() and not SKIPPED_DIRS & set(p.parts)
        ]


def test_detector_catches_real_looking_secrets():
    discord = "M" + "A" * 23 + "." + "B" * 6 + "." + "C" * 30
    github = "ghp_" + "a" * 36
    private = "-----BEGIN " + "OPENSSH PRIVATE KEY-----"
    aws = "AKIA" + "A" * 16
    assigned = "DISCORD_TOKEN=" + "x" * 30

    assert find_secrets(f"token {discord}") == ["token de Discord"]
    assert "token de GitHub" in find_secrets(github)
    assert "clave privada" in find_secrets(private)
    assert "clave de AWS" in find_secrets(aws)
    assert "secreto asignado" in find_secrets(assigned)


@pytest.mark.parametrize(
    "harmless",
    [
        "DISCORD_TOKEN=",
        "RESOLVER_API_KEY=",
        "RESOLVER_API_KEY_SHA256=" + "a" * 64,
        'monkeypatch.setenv("DISCORD_TOKEN", "valor")',
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "resolver.presentation.auth.verify_api_key",
    ],
)
def test_detector_ignores_harmless_text(harmless):
    assert find_secrets(harmless) == []


def test_no_tracked_file_contains_a_secret():
    findings = {}
    for name in tracked_files():
        path = ROOT / name
        if path.is_file() and path.name != "test_no_secrets.py":
            try:
                text = path.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if found := find_secrets(text):
                findings[name] = found

    assert not findings, f"Posibles secretos en archivos versionados: {findings}"


def test_no_tracked_file_has_a_name_that_suggests_a_secret():
    suspicious = [n for n in tracked_files() if FORBIDDEN_NAMES.search(n)]

    assert not suspicious, f"Archivos con nombre de secreto versionados: {suspicious}"


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        "cookies.txt",
        "data/cookies/cookies.txt",
        "secrets/discord_token",
        "clave.pem",
        "x.key",
    ],
)
def test_gitignore_covers_secret_locations(path):
    result = subprocess.run(
        ["git", "check-ignore", "-q", path], cwd=ROOT, capture_output=True, check=False
    )

    assert result.returncode == 0, f"{path} no está ignorado por git"
