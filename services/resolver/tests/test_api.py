import pytest
from fastapi.testclient import TestClient

from resolver.domain.errors import BotDetectedError, TrackNotFoundError, UnsupportedInputError
from resolver.domain.models import CollectionKind, Resolution, StreamInfo
from resolver.presentation.api import create_app


class StubService:
    def __init__(self, make_track):
        self.make_track = make_track
        self.error = None

    async def resolve(self, text):
        if self.error:
            raise self.error
        return Resolution(CollectionKind.TRACK, "Song", (self.make_track("Song"),))

    async def stream(self, track):
        if self.error:
            raise self.error
        return StreamInfo(
            url="https://audio",
            headers={"User-Agent": "x"},
            expires_at=99,
            webpage_url=track.webpage_url,
        )


@pytest.fixture
def service(make_track):
    return StubService(make_track)


@pytest.fixture
def client(service):
    with TestClient(create_app(service)) as test_client:
        yield test_client


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_resolve_returns_tracks(client):
    response = client.post("/v1/resolve", json={"query": "song"})

    body = response.json()
    assert response.status_code == 200
    assert body["kind"] == "track"
    assert body["tracks"][0]["title"] == "Song"
    assert body["truncated"] is False


def test_resolve_rejects_empty_query(client):
    assert client.post("/v1/resolve", json={"query": ""}).status_code == 422


def test_stream_returns_url_and_headers(client):
    track = {
        "title": "Song",
        "source": "youtube",
        "webpage_url": "https://www.youtube.com/watch?v=a",
    }

    body = client.post("/v1/stream", json=track).json()

    assert body["url"] == "https://audio"
    assert body["headers"] == {"User-Agent": "x"}
    assert body["expires_at"] == 99


@pytest.mark.parametrize(
    ("error", "status", "code"),
    [
        (UnsupportedInputError("no"), 422, "unsupported_input"),
        (TrackNotFoundError("no"), 404, "not_found"),
        (BotDetectedError("bot"), 503, "bot_detected"),
    ],
)
def test_domain_errors_map_to_status_and_code(client, service, error, status, code):
    service.error = error

    response = client.post("/v1/resolve", json={"query": "x"})

    assert response.status_code == status
    assert response.json() == {"code": code, "message": error.message}


async def test_shutdown_hook_runs(service):
    closed = []

    async def on_shutdown():
        closed.append(True)

    with TestClient(create_app(service, on_shutdown)):
        pass

    assert closed == [True]
