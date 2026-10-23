import httpx
import pytest

from bot.domain.errors import ResolverError
from bot.domain.models import Source as BotSource
from bot.infrastructure.resolver_client import HttpTrackResolver
from resolver.domain.errors import BotDetectedError
from resolver.domain.models import CollectionKind, Resolution, Source, StreamInfo, Track
from resolver.presentation.api import create_app


class StubResolverService:
    def __init__(self):
        self.error = None
        self.streamed = []

    async def resolve(self, text):
        if self.error:
            raise self.error
        spotify = Track(
            title="Song",
            artist="Artist",
            duration_seconds=180,
            source=Source.SPOTIFY,
            search_query="Artist - Song",
        )
        return Resolution(CollectionKind.PLAYLIST, "Mix", (spotify,), truncated=True)

    async def stream(self, track):
        self.streamed.append(track)
        return StreamInfo(
            url="https://audio", headers={"User-Agent": "x"}, expires_at=5, webpage_url="https://w"
        )


@pytest.fixture
def service():
    return StubResolverService()


@pytest.fixture
def bot_side(service):
    transport = httpx.ASGITransport(app=create_app(service))
    client = httpx.AsyncClient(transport=transport, base_url="http://resolver")
    return HttpTrackResolver(client)


async def test_bot_client_understands_resolver_resolve_response(bot_side):
    result = await bot_side.resolve("anything")

    assert result.title == "Mix"
    assert result.truncated
    assert result.tracks[0].source == BotSource.SPOTIFY
    assert result.tracks[0].search_query == "Artist - Song"
    assert result.tracks[0].webpage_url is None


async def test_resolver_accepts_what_the_bot_sends_for_stream(bot_side, service):
    track = (await bot_side.resolve("anything")).tracks[0]

    stream = await bot_side.stream(track)

    assert stream.url == "https://audio"
    assert service.streamed[0].search_query == "Artist - Song"
    assert service.streamed[0].duration_seconds == 180


async def test_bot_client_understands_resolver_errors(bot_side, service):
    service.error = BotDetectedError("bloqueado")

    with pytest.raises(ResolverError) as caught:
        await bot_side.resolve("anything")

    assert caught.value.code == "bot_detected"
    assert caught.value.user_message == "bloqueado"
