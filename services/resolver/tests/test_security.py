import hmac
import logging

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from resolver.application.intent import ensure_youtube_video
from resolver.application.service import ResolverService
from resolver.config import Settings
from resolver.domain.errors import UnsupportedInputError
from resolver.domain.models import CollectionKind, Resolution, Source, StreamInfo, Track
from resolver.infrastructure.log_redaction import RedactingFilter, redact
from resolver.infrastructure.ytdlp_extractor import is_shared
from resolver.presentation import auth
from resolver.presentation.api import create_app
from resolver.presentation.auth import hash_api_key
from resolver.presentation.security import SecurityPolicy

KEY = "clave-de-prueba-larga-y-aleatoria"
FAKE_TOKEN = "M" + "A" * 23 + "." + "GabcDe" + "." + "x" * 27
TRACK = {
    "title": "T",
    "source": "youtube",
    "webpage_url": "https://www.youtube.com/watch?v=abcdefghijk",
}
HOSTILE_URLS = [
    "http://169.254.169.254/latest/meta-data/",
    "http://localhost:8080/health",
    "http://127.0.0.1/admin",
    "http://[::1]/",
    "file:///etc/passwd",
    "https://evil.example/watch?v=abc",
    "https://www.youtube.com.evil.example/watch?v=abc",
    "https://evil.example/https://www.youtube.com/watch?v=abc",
    "ftp://www.youtube.com/watch?v=abc",
    "https://open.spotify.com/track/abc",
    "no es una url",
]


class SpyExtractor:
    def __init__(self):
        self.fetched = []

    async def stream(self, url):
        self.fetched.append(url)
        return StreamInfo(url="https://audio", headers={}, expires_at=None, webpage_url=url)

    async def search(self, query, count):
        return []


@pytest.mark.parametrize("url", HOSTILE_URLS)
def test_stream_url_must_be_a_youtube_video(url):
    with pytest.raises(UnsupportedInputError):
        ensure_youtube_video(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://youtu.be/dQw4w9WgXcQ",
        "https://music.youtube.com/watch?v=dQw4w9WgXcQ",
        "https://www.youtube.com/shorts/abcdefghijk",
    ],
)
def test_legitimate_youtube_urls_are_accepted_and_rebuilt_canonically(url):
    video_id = url[-11:]

    assert ensure_youtube_video(url) == f"https://www.youtube.com/watch?v={video_id}"


@pytest.mark.parametrize("url", HOSTILE_URLS)
async def test_service_never_hands_hostile_urls_to_the_extractor(url):
    spy = SpyExtractor()
    track = Track(
        title="x", artist=None, duration_seconds=None, source=Source.YOUTUBE, webpage_url=url
    )

    with pytest.raises(UnsupportedInputError):
        await ResolverService(spy, None, 10).stream(track)

    assert spy.fetched == []


class StubService:
    async def resolve(self, text):
        return Resolution(CollectionKind.TRACK, "T", ())

    async def stream(self, track):
        return StreamInfo(url="https://audio", headers={}, expires_at=None, webpage_url="w")


@pytest.fixture
def secured():
    with TestClient(
        create_app(StubService(), security=SecurityPolicy(api_key_sha256=hash_api_key(KEY)))
    ) as client:
        yield client


def bearer(value):
    return {"Authorization": f"Bearer {value}"}


def test_requests_without_credentials_are_rejected(secured):
    response = secured.post("/v1/resolve", json={"query": "x"})

    assert response.status_code == 401
    assert response.json()["code"] == "unauthorized"


@pytest.mark.parametrize(
    "headers",
    [
        bearer("clave-equivocada"),
        bearer(""),
        {"Authorization": KEY},
        {"Authorization": f"Basic {KEY}"},
    ],
)
def test_wrong_credentials_are_rejected(secured, headers):
    assert secured.post("/v1/resolve", json={"query": "x"}, headers=headers).status_code == 401
    assert secured.post("/v1/stream", json=TRACK, headers=headers).status_code == 401


def test_correct_key_is_accepted_on_every_endpoint(secured):
    assert secured.post("/v1/resolve", json={"query": "x"}, headers=bearer(KEY)).status_code == 200
    assert secured.post("/v1/stream", json=TRACK, headers=bearer(KEY)).status_code == 200


def test_scheme_is_case_insensitive(secured):
    headers = {"Authorization": f"bearer {KEY}"}

    assert secured.post("/v1/resolve", json={"query": "x"}, headers=headers).status_code == 200


def test_health_stays_open_for_container_healthchecks(secured):
    assert secured.get("/health").status_code == 200


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/openapi.json"])
def test_api_documentation_is_not_exposed(secured, path):
    assert secured.get(path).status_code == 404


def test_without_configured_hash_the_api_stays_open_for_local_development():
    with TestClient(create_app(StubService())) as client:
        assert client.post("/v1/resolve", json={"query": "x"}).status_code == 200


def test_key_comparison_is_constant_time(monkeypatch):
    calls = []
    original = hmac.compare_digest
    monkeypatch.setattr(auth.hmac, "compare_digest", lambda a, b: calls.append(1) or original(a, b))

    with TestClient(
        create_app(StubService(), security=SecurityPolicy(api_key_sha256=hash_api_key(KEY)))
    ) as client:
        client.post("/v1/resolve", json={"query": "x"}, headers=bearer("otra"))

    assert calls


def test_hash_is_sha256_hex_and_never_equals_the_key():
    digest = hash_api_key(KEY)

    assert len(digest) == 64
    assert digest != KEY
    assert hash_api_key(KEY) == digest


def test_uppercase_configured_hash_still_matches():
    policy = SecurityPolicy(api_key_sha256=hash_api_key(KEY).upper())
    app = create_app(StubService(), security=policy)

    with TestClient(app) as client:
        assert (
            client.post("/v1/resolve", json={"query": "x"}, headers=bearer(KEY)).status_code == 200
        )


def test_config_rejects_a_plain_key_pasted_instead_of_its_hash(monkeypatch):
    monkeypatch.setenv("RESOLVER_API_KEY_SHA256", KEY)
    monkeypatch.chdir("/")

    with pytest.raises(ValidationError):
        Settings()


def test_config_accepts_a_real_digest(monkeypatch):
    monkeypatch.setenv("RESOLVER_API_KEY_SHA256", hash_api_key(KEY))
    monkeypatch.chdir("/")

    assert Settings().resolver_api_key_sha256 == hash_api_key(KEY)


def test_oversized_fields_are_rejected(secured):
    huge = {**TRACK, "title": "x" * 5000}

    assert secured.post("/v1/stream", json=huge, headers=bearer(KEY)).status_code == 422
    assert (
        secured.post("/v1/resolve", json={"query": "x" * 501}, headers=bearer(KEY)).status_code
        == 422
    )


@pytest.mark.parametrize(
    ("secret", "text"),
    [
        ("abc123def456", "Authorization: Bearer abc123def456 enviado"),
        (
            "SIGNATURESECRET",
            "https://r1.googlevideo.com/videoplayback?expire=1&sig=SIGNATURESECRET&id=2",
        ),
        ("203.0.113.9", "https://r1.googlevideo.com/videoplayback?id=2&ip=203.0.113.9&itag=1"),
        ("SESSIONVALUE", "Cookie: SID=SESSIONVALUE; HSID=otro"),
        ("secret-account", "cookies file not found: /data/cookies/secret-account.txt"),
        (FAKE_TOKEN, f"token {FAKE_TOKEN} fin"),
    ],
)
def test_redaction_hides_sensitive_values(secret, text):
    assert secret not in redact(text)


def test_redaction_keeps_ordinary_text_intact():
    text = "Resolviendo https://www.youtube.com/watch?v=dQw4w9WgXcQ para el servidor 42"

    assert redact(text) == text


def test_filter_redacts_formatted_log_records():
    record = logging.LogRecord(
        "x", logging.WARNING, "f", 1, "falla %s", ("Bearer topsecretvalue",), None
    )

    RedactingFilter().filter(record)

    assert "topsecretvalue" not in record.getMessage()


@pytest.mark.parametrize(
    ("mode", "shared"),
    [(0o600, False), (0o400, False), (0o640, True), (0o644, True), (0o666, True)],
)
def test_is_shared_detects_group_and_world_access(mode, shared):
    assert is_shared(mode) is shared


@pytest.mark.parametrize("body", [b'{"query": "\ud800"}', b'{"query": "a\udfffb"}'])
def test_invalid_unicode_gets_a_clean_422_instead_of_crashing_the_response(secured, body):
    response = secured.post(
        "/v1/resolve", content=body, headers={**bearer(KEY), "Content-Type": "application/json"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"
    assert "ud800" not in response.text


def test_invalid_unicode_in_a_track_is_rejected_cleanly(secured):
    body = b'{"title": "ok\\ud800", "source": "youtube"}'

    response = secured.post(
        "/v1/stream", content=body, headers={**bearer(KEY), "Content-Type": "application/json"}
    )

    assert response.status_code == 422
    assert response.json()["code"] == "invalid_request"


def test_validation_errors_never_echo_what_the_client_sent(secured):
    secret = "valor-que-no-debe-volver"

    response = secured.post(
        "/v1/stream", json={"title": secret, "source": "no-existe"}, headers=bearer(KEY)
    )

    assert response.status_code == 422
    assert secret not in response.text
    assert "source" in response.json()["fields"]
