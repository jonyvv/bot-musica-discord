import httpx
import pytest

from bot.domain.errors import ResolverError, ResolverUnavailableError
from bot.domain.models import CollectionKind, Source
from bot.infrastructure.resolver_client import HttpTrackResolver

TRACK = {
    "title": "Song",
    "artist": "Artist",
    "duration_seconds": 200,
    "source": "youtube",
    "webpage_url": "https://www.youtube.com/watch?v=abc",
    "search_query": None,
    "thumbnail_url": None,
    "is_live": False,
}


def resolver_for(handler):
    client = httpx.AsyncClient(base_url="http://resolver", transport=httpx.MockTransport(handler))
    return HttpTrackResolver(client)


def json_response(body, status=200):
    return lambda request: httpx.Response(status, json=body)


async def test_resolve_parses_tracks():
    body = {"kind": "playlist", "title": "Mix", "tracks": [TRACK], "truncated": True}

    result = await resolver_for(json_response(body)).resolve("mix")

    assert result.kind == CollectionKind.PLAYLIST
    assert result.title == "Mix"
    assert result.truncated
    assert result.tracks[0].title == "Song"
    assert result.tracks[0].source == Source.YOUTUBE
    assert result.tracks[0].requester_id is None


async def test_resolve_sends_query():
    seen = {}

    def handler(request):
        seen["path"] = request.url.path
        seen["body"] = request.read()
        return httpx.Response(
            200, json={"kind": "track", "title": None, "tracks": [], "truncated": False}
        )

    await resolver_for(handler).resolve("dua lipa")

    assert seen["path"] == "/v1/resolve"
    assert b"dua lipa" in seen["body"]


async def test_stream_sends_track_without_requester_and_parses_response():
    seen = {}

    def handler(request):
        seen["body"] = request.read()
        return httpx.Response(
            200,
            json={
                "url": "https://audio",
                "headers": {"User-Agent": "x"},
                "expires_at": 9,
                "webpage_url": "https://w",
            },
        )

    track = (
        await resolver_for(
            json_response({"kind": "track", "title": None, "tracks": [TRACK], "truncated": False})
        ).resolve("x")
    ).tracks[0]
    stream = await resolver_for(handler).stream(track)

    assert b"requester_id" not in seen["body"]
    assert stream.url == "https://audio"
    assert stream.headers == {"User-Agent": "x"}
    assert stream.expires_at == 9


async def test_service_error_keeps_code_and_message():
    body = {"code": "bot_detected", "message": "YouTube bloqueo la consulta"}

    with pytest.raises(ResolverError) as caught:
        await resolver_for(json_response(body, 503)).resolve("x")

    assert caught.value.code == "bot_detected"
    assert caught.value.user_message == "YouTube bloqueo la consulta"


async def test_unparseable_error_becomes_generic_message():
    with pytest.raises(ResolverError) as caught:
        await resolver_for(lambda request: httpx.Response(500, text="boom")).resolve("x")

    assert "error" in caught.value.user_message.lower()


async def test_connection_failure_is_reported_as_unavailable():
    def handler(request):
        raise httpx.ConnectError("refused")

    with pytest.raises(ResolverUnavailableError):
        await resolver_for(handler).resolve("x")


async def test_timeout_is_reported_as_unavailable():
    def handler(request):
        raise httpx.ReadTimeout("slow")

    with pytest.raises(ResolverUnavailableError) as caught:
        await resolver_for(handler).resolve("x")

    assert "tard" in caught.value.user_message
