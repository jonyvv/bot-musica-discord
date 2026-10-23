import asyncio
import contextlib

import pytest

from resolver.domain.errors import BotDetectedError, TrackUnavailableError
from resolver.domain.models import Resolution, StreamInfo, Track
from resolver.infrastructure.pacing import Pacer
from resolver.infrastructure.protection import CircuitBreaker, ProtectedExtractor

URL = "https://www.youtube.com/watch?v=abcdefghijk"


class FakeClock:
    def __init__(self, start=1000.0):
        self.now = start

    def __call__(self):
        return self.now


class CountingExtractor:
    def __init__(self, delay=0.0):
        self.calls = []
        self.delay = delay
        self.error = None
        self.active = 0
        self.peak = 0
        self.expires_at = None

    async def _record(self, name, value):
        self.calls.append(name)
        self.active += 1
        self.peak = max(self.peak, self.active)
        try:
            await asyncio.sleep(self.delay)
            if self.error:
                raise self.error
            return value
        finally:
            self.active -= 1

    async def video(self, url):
        return await self._record("video", Track("T", None, 1, None, url))

    async def playlist(self, url, limit):
        return await self._record("playlist", Resolution(None, "P", ()))

    async def search(self, query, count):
        return await self._record("search", [])

    async def stream(self, url):
        info = StreamInfo(url="https://a", headers={}, expires_at=self.expires_at, webpage_url=url)
        return await self._record("stream", info)


@pytest.fixture
def clock():
    return FakeClock()


@pytest.fixture
def inner():
    return CountingExtractor()


def protected(inner, clock, **overrides):
    options = {
        "pacer": Pacer(10, 0),
        "breaker": CircuitBreaker(3, 600, clock),
        "ttl_seconds": 600,
        "clock": clock,
        "wall_clock": clock,
    }
    return ProtectedExtractor(inner, **{**options, **overrides})


async def test_repeated_requests_are_served_from_cache(inner, clock):
    extractor = protected(inner, clock)

    for _ in range(25):
        await extractor.video(URL)

    assert inner.calls == ["video"]


async def test_a_flood_of_identical_concurrent_requests_makes_a_single_upstream_call(clock):
    inner = CountingExtractor(delay=0.05)
    extractor = protected(inner, clock)

    results = await asyncio.gather(*(extractor.stream(URL) for _ in range(200)))

    assert inner.calls == ["stream"]
    assert len({id(r) for r in results}) == 1


async def test_different_requests_are_not_mixed_up(inner, clock):
    extractor = protected(inner, clock)

    await extractor.video(URL)
    await extractor.video(URL.replace("abc", "xyz"))
    await extractor.search("a", 5)
    await extractor.search("a", 10)

    assert inner.calls == ["video", "video", "search", "search"]


async def test_cache_entries_expire(inner, clock):
    extractor = protected(inner, clock, ttl_seconds=60)
    await extractor.video(URL)

    clock.now += 61
    await extractor.video(URL)

    assert inner.calls == ["video", "video"]


async def test_streams_are_not_cached_past_their_url_expiry(inner, clock):
    inner.expires_at = clock.now + 30
    extractor = protected(inner, clock)

    await extractor.stream(URL)
    await extractor.stream(URL)

    assert inner.calls == ["stream", "stream"]


async def test_streams_are_cached_until_shortly_before_expiry(inner, clock):
    inner.expires_at = clock.now + 3600
    extractor = protected(inner, clock)

    await extractor.stream(URL)
    clock.now += 500
    await extractor.stream(URL)

    assert inner.calls == ["stream"]


async def test_errors_are_not_cached(inner, clock):
    extractor = protected(inner, clock)
    inner.error = TrackUnavailableError("privado")

    with pytest.raises(TrackUnavailableError):
        await extractor.video(URL)
    inner.error = None
    await extractor.video(URL)

    assert inner.calls == ["video", "video"]


async def test_cache_size_is_bounded(inner, clock):
    extractor = protected(inner, clock, max_entries=50)

    for i in range(500):
        await extractor.search(f"consulta {i}", 5)

    assert len(extractor._cache) <= 50


async def test_circuit_opens_after_repeated_bot_detection_and_stops_hitting_youtube(inner, clock):
    extractor = protected(inner, clock)
    inner.error = BotDetectedError("bloqueado")

    for i in range(3):
        with pytest.raises(BotDetectedError):
            await extractor.search(f"q{i}", 5)
    upstream_before = len(inner.calls)
    for i in range(50):
        with pytest.raises(BotDetectedError):
            await extractor.search(f"otra{i}", 5)

    assert upstream_before == 3
    assert len(inner.calls) == 3


async def test_circuit_closes_after_the_cooldown(inner, clock):
    extractor = protected(inner, clock)
    inner.error = BotDetectedError("bloqueado")
    for i in range(3):
        with pytest.raises(BotDetectedError):
            await extractor.search(f"q{i}", 5)

    clock.now += 601
    inner.error = None
    await extractor.search("nueva", 5)

    assert len(inner.calls) == 4


async def test_one_more_failure_after_the_cooldown_reopens_the_circuit(inner, clock):
    extractor = protected(inner, clock)
    inner.error = BotDetectedError("bloqueado")
    for i in range(3):
        with pytest.raises(BotDetectedError):
            await extractor.search(f"q{i}", 5)
    clock.now += 601

    with pytest.raises(BotDetectedError):
        await extractor.search("prueba", 5)
    with pytest.raises(BotDetectedError):
        await extractor.search("inmediata", 5)

    assert len(inner.calls) == 4


async def test_ordinary_errors_do_not_trip_the_circuit(inner, clock):
    extractor = protected(inner, clock)
    inner.error = TrackUnavailableError("privado")

    for i in range(20):
        with pytest.raises(TrackUnavailableError):
            await extractor.video(f"{URL}{i}")

    assert len(inner.calls) == 20


async def test_a_success_resets_the_failure_count(inner, clock):
    extractor = protected(inner, clock)
    for outcome in (BotDetectedError("x"), BotDetectedError("x"), None, BotDetectedError("x")):
        inner.error = outcome
        with contextlib.suppress(BotDetectedError):
            await extractor.search(f"q{len(inner.calls)}", 5)

    inner.error = None
    await extractor.search("sigue disponible", 5)

    assert len(inner.calls) == 5


async def test_concurrency_towards_youtube_is_capped(clock):
    inner = CountingExtractor(delay=0.02)
    extractor = protected(inner, clock, pacer=Pacer(3, 0))

    await asyncio.gather(*(extractor.search(f"q{i}", 5) for i in range(40)))

    assert inner.peak == 3


async def test_requests_are_spaced_by_the_minimum_interval():
    clock = FakeClock()
    waits = []

    async def sleep(seconds):
        waits.append(round(seconds, 3))
        clock.now += seconds

    pacer = Pacer(5, 0.5, clock=clock, sleep=sleep)

    for _ in range(4):
        async with pacer:
            pass

    assert waits == [0.5, 0.5, 0.5]


async def test_pacer_releases_its_slot_when_the_call_fails():
    pacer = Pacer(1, 0)

    with pytest.raises(ValueError):
        async with pacer:
            raise ValueError

    async with asyncio.timeout(1):
        async with pacer:
            pass
