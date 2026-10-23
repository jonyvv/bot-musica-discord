import pytest

from bot.application.session import GuildSession, SessionSettings
from bot.domain.errors import ResolverError
from bot.domain.models import CollectionKind, Resolution, Source, StreamInfo, Track


class FakeResolver:
    def __init__(self):
        self.resolution = Resolution(CollectionKind.TRACK, None, ())
        self.failing_titles = set()
        self.queries = []
        self.streamed = []

    async def resolve(self, query):
        self.queries.append(query)
        return self.resolution

    async def stream(self, track):
        if track.title in self.failing_titles:
            raise ResolverError("no esta disponible")
        self.streamed.append(track.title)
        return StreamInfo(url=f"audio:{track.title}", headers={}, expires_at=None, webpage_url="u")


class FakeVoice:
    def __init__(self):
        self.connected = False
        self.channel = None
        self.connects = []
        self.played = []
        self.volumes = []
        self.stops = 0
        self.disconnects = 0
        self.paused = False
        self.on_finished = None

    @property
    def is_connected(self):
        return self.connected

    @property
    def channel_id(self):
        return self.channel

    async def connect(self, channel_id):
        self.connected, self.channel = True, channel_id
        self.connects.append(channel_id)

    async def disconnect(self):
        self.connected, self.channel = False, None
        self.disconnects += 1

    async def play(self, stream, volume, on_finished):
        self.played.append(stream.url)
        self.volumes.append(volume)
        self.on_finished = on_finished

    def pause(self):
        self.paused = True

    def resume(self):
        self.paused = False

    def stop(self):
        self.stops += 1

    def set_volume(self, volume):
        self.volumes.append(volume)

    async def finish(self, error=None):
        await self.on_finished(error)


class FakeNotifier:
    def __init__(self):
        self.messages = []
        self.channel = None

    def bind(self, channel_id):
        self.channel = channel_id

    async def send(self, text):
        self.messages.append(text)


class RecordingObserver:
    def __init__(self):
        self.events = []

    def playing(self):
        self.events.append("playing")

    def paused(self):
        self.events.append("paused")

    def idle(self):
        self.events.append("idle")

    def channel_empty(self):
        self.events.append("channel_empty")

    def channel_occupied(self):
        self.events.append("channel_occupied")

    def close(self):
        self.events.append("close")


@pytest.fixture
def make_track():
    def factory(
        title="Song", duration=200, url="https://www.youtube.com/watch?v=abcdefghijk", **extra
    ):
        return Track(
            title=title,
            artist=extra.pop("artist", "Artist"),
            duration_seconds=duration,
            source=extra.pop("source", Source.YOUTUBE),
            webpage_url=url,
            **extra,
        )

    return factory


@pytest.fixture
def resolve_to(make_track):
    def factory(resolver, *titles):
        tracks = tuple(make_track(title) for title in titles)
        resolver.resolution = Resolution(CollectionKind.PLAYLIST, "List", tracks)

    return factory


@pytest.fixture
def resolver():
    return FakeResolver()


@pytest.fixture
def voice():
    return FakeVoice()


@pytest.fixture
def notifier():
    return FakeNotifier()


@pytest.fixture
def observer():
    return RecordingObserver()


@pytest.fixture
def closed_guilds():
    return []


@pytest.fixture
def session(resolver, voice, notifier, observer, closed_guilds):
    return GuildSession(
        guild_id=1,
        resolver=resolver,
        voice=voice,
        notifier=notifier,
        settings=SessionSettings(default_volume=50, max_queue_size=5),
        activity_factory=lambda close: observer,
        on_closed=closed_guilds.append,
    )


@pytest.fixture(autouse=True)
def isolated_secret_store(monkeypatch):
    """Evita que los tests lean secretos guardados de verdad en el almacén del sistema."""
    monkeypatch.setattr("bot.main.load_secret", lambda name: None)
