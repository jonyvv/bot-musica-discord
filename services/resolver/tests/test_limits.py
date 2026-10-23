import asyncio
import contextlib
import time
from typing import ClassVar

import pytest
from fastapi.testclient import TestClient

from resolver.application.service import ResolverService
from resolver.domain.errors import TrackUnavailableError
from resolver.domain.models import CollectionKind, Resolution, Source, StreamInfo, Track
from resolver.domain.policy import exceeds_limits
from resolver.infrastructure.ytdlp_extractor import YtDlpExtractor, YtDlpOptions
from resolver.presentation.api import create_app
from resolver.presentation.auth import hash_api_key
from resolver.presentation.inflight_limit import InflightLimitMiddleware
from resolver.presentation.security import SecurityPolicy, SlidingWindowLimiter

KEY = "clave-de-prueba-larga-y-aleatoria"
URL = "https://www.youtube.com/watch?v=abcdefghijk"
MEDIA = "https://rr1---sn-abc.googlevideo.com/videoplayback?id=1"


async def always_playable(stream):
    return True


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


class StubService:
    async def resolve(self, text):
        return Resolution(CollectionKind.TRACK, "T", ())

    async def stream(self, track):
        return StreamInfo(url="https://a", headers={}, expires_at=None, webpage_url="w")


def client_with(**policy):
    return TestClient(create_app(StubService(), security=SecurityPolicy(**policy)))


def test_limiter_allows_up_to_the_limit_then_reports_the_wait():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(3, 60, clock)

    assert [limiter.hit("a") for _ in range(3)] == [None, None, None]
    assert limiter.hit("a") == pytest.approx(60)

    clock.now += 30
    assert limiter.hit("a") == pytest.approx(30)


def test_limiter_recovers_when_the_window_slides():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(2, 60, clock)
    limiter.hit("a")
    limiter.hit("a")

    clock.now += 61

    assert limiter.hit("a") is None


def test_limiter_keys_are_independent():
    limiter = SlidingWindowLimiter(1, 60, FakeClock())
    limiter.hit("atacante")

    assert limiter.hit("atacante") is not None
    assert limiter.hit("legitimo") is None


def test_limiter_memory_is_bounded_against_many_distinct_clients():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(5, 60, clock, max_keys=1000)

    for i in range(20_000):
        limiter.hit(f"10.0.{i // 250}.{i % 250}")

    assert len(limiter._events) <= 1000


def test_request_flood_is_cut_off_with_429_and_retry_after():
    with client_with(requests_per_minute=10) as client:
        statuses = [client.post("/v1/resolve", json={"query": "x"}).status_code for _ in range(60)]
        blocked = client.post("/v1/resolve", json={"query": "x"})

    assert statuses.count(200) == 10
    assert statuses.count(429) == 50
    assert blocked.json()["code"] == "rate_limited"
    assert int(blocked.headers["Retry-After"]) >= 1


def test_health_endpoint_is_not_throttled_so_orchestrators_keep_working():
    with client_with(requests_per_minute=1) as client:
        statuses = {client.get("/health").status_code for _ in range(100)}

    assert statuses == {200}


def test_brute_forcing_the_key_locks_the_client_out():
    with client_with(api_key_sha256=hash_api_key(KEY), auth_failure_limit=5) as client:
        guesses = [
            client.post(
                "/v1/resolve", json={"query": "x"}, headers={"Authorization": f"Bearer guess{i}"}
            ).status_code
            for i in range(30)
        ]
        with_real_key = client.post(
            "/v1/resolve", json={"query": "x"}, headers={"Authorization": f"Bearer {KEY}"}
        )

    assert guesses[:5] == [401] * 5
    assert set(guesses[5:]) == {429}
    assert with_real_key.status_code == 429


def test_lockout_does_not_apply_to_a_client_that_never_fails():
    with client_with(api_key_sha256=hash_api_key(KEY), auth_failure_limit=3) as client:
        statuses = [
            client.post(
                "/v1/resolve", json={"query": "x"}, headers={"Authorization": f"Bearer {KEY}"}
            ).status_code
            for _ in range(20)
        ]

    assert set(statuses) == {200}


def test_oversized_declared_body_is_rejected_before_parsing():
    with client_with(max_body_bytes=2048) as client:
        response = client.post("/v1/resolve", content=b"x" * 1_000_000)

    assert response.status_code == 413
    assert response.json()["code"] == "payload_too_large"


def test_oversized_streamed_body_without_content_length_is_rejected():
    def endless():
        for _ in range(500):
            yield b'{"query": "' + b"a" * 4096

    with client_with(max_body_bytes=8192) as client:
        response = client.post("/v1/resolve", content=endless())

    assert response.status_code == 413


def test_normal_sized_requests_still_work_with_the_body_limit():
    with client_with(max_body_bytes=2048) as client:
        assert client.post("/v1/resolve", json={"query": "x" * 400}).status_code == 200


@pytest.mark.parametrize(
    ("duration", "live", "expected"),
    [
        (200, False, False),
        (None, False, False),
        (10_800, False, False),
        (10_801, False, True),
        (86_400, False, True),
        (100, True, True),
        (None, True, True),
    ],
)
def test_exceeds_limits(duration, live, expected):
    assert exceeds_limits(duration, live, 10_800) is expected


def test_zero_max_disables_the_duration_limit_but_never_allows_live_streams():
    assert exceeds_limits(999_999, False, 0) is False
    assert exceeds_limits(10, True, 0) is True


class StaticExtractor:
    def __init__(self, tracks):
        self.tracks = tracks

    async def video(self, url):
        return self.tracks[0]

    async def playlist(self, url, limit):
        return Resolution(CollectionKind.PLAYLIST, "P", tuple(self.tracks))

    async def search(self, query, count):
        return list(self.tracks)


def track(title, duration, live=False):
    return Track(title, None, duration, Source.YOUTUBE, URL, is_live=live)


async def test_playlist_drops_live_and_overlong_entries_and_flags_it():
    items = [track("ok", 200), track("loop 10h", 36_000), track("en vivo", None, live=True)]
    service = ResolverService(StaticExtractor(items), None, 500, 10_800)

    result = await service.resolve("https://www.youtube.com/playlist?list=PLabcdefghij")

    assert [t.title for t in result.tracks] == ["ok"]
    assert result.truncated


async def test_a_single_overlong_video_is_rejected_outright():
    service = ResolverService(StaticExtractor([track("10 horas", 36_000)]), None, 500, 10_800)

    with pytest.raises(TrackUnavailableError):
        await service.resolve(URL)


async def test_a_live_stream_is_rejected_outright():
    service = ResolverService(StaticExtractor([track("directo", None, live=True)]), None, 500)

    with pytest.raises(TrackUnavailableError):
        await service.resolve(URL)


class FakeYoutubeDL:
    info: ClassVar[dict] = {}

    def __init__(self, params):
        pass

    def extract_info(self, target, download=False):
        return dict(self.info)

    def sanitize_info(self, info):
        return info

    def close(self):
        pass


@pytest.mark.parametrize(
    "info",
    [
        {"url": MEDIA, "duration": 99_999},
        {"url": MEDIA, "is_live": True},
        {"url": MEDIA, "live_status": "is_live"},
    ],
)
async def test_stream_refuses_infinite_or_overlong_audio_even_when_the_listing_hid_it(
    monkeypatch, info
):
    FakeYoutubeDL.info = info
    monkeypatch.setattr("resolver.infrastructure.ytdlp_extractor.YoutubeDL", FakeYoutubeDL)

    with pytest.raises(TrackUnavailableError):
        await YtDlpExtractor(YtDlpOptions(max_track_seconds=10_800)).stream(URL)


async def test_stream_accepts_normal_audio(monkeypatch):
    FakeYoutubeDL.info = {"url": MEDIA, "duration": 200, "http_headers": {}}
    monkeypatch.setattr("resolver.infrastructure.ytdlp_extractor.YoutubeDL", FakeYoutubeDL)

    stream = await YtDlpExtractor(YtDlpOptions(), probe=always_playable).stream(URL)

    assert stream.url == MEDIA


def test_hostile_regex_inputs_do_not_cause_catastrophic_backtracking():
    from resolver.application.intent import classify
    from resolver.domain.errors import UnsupportedInputError
    from resolver.infrastructure.log_redaction import redact

    nasty = ["a" * 100_000, "/" * 100_000, "https://" + "a." * 50_000, "?" + "&k=v" * 25_000]
    started = time.perf_counter()
    for text in nasty:
        redact(text)
        with contextlib.suppress(UnsupportedInputError):
            classify(text)

    assert time.perf_counter() - started < 5


class Gate:
    def __init__(self):
        self.release = asyncio.Event()
        self.running = 0
        self.peak = 0

    async def app(self, scope, receive, send):
        if scope["path"] != "/health":
            self.running += 1
            self.peak = max(self.peak, self.running)
            try:
                await self.release.wait()
            finally:
                self.running -= 1
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})


class Collector:
    def __init__(self):
        self.messages = []

    async def __call__(self, message):
        self.messages.append(message)

    @property
    def status(self):
        return self.messages[0]["status"]


def scope_for(client, path="/v1/resolve"):
    return {"type": "http", "path": path, "client": (client, 5555), "headers": []}


async def call(middleware, client, path="/v1/resolve"):
    out = Collector()
    await middleware(scope_for(client, path), None, out)
    return out


async def test_one_client_cannot_hold_more_than_its_share_of_concurrent_requests():
    gate = Gate()
    middleware = InflightLimitMiddleware(gate.app, per_client=4)
    tasks = [asyncio.create_task(call(middleware, "atacante")) for _ in range(40)]
    await asyncio.sleep(0.05)

    rejected = [t.result() for t in tasks if t.done()]
    gate.release.set()
    served = [t for t in tasks if t not in {t for t in tasks if t.done()}]
    await asyncio.gather(*tasks)

    assert gate.peak == 4
    assert len(rejected) == 36
    assert all(r.status == 429 for r in rejected)
    assert len(served) == 4


async def test_a_flooding_client_does_not_take_slots_from_a_legitimate_one():
    gate = Gate()
    middleware = InflightLimitMiddleware(gate.app, per_client=4)
    flood = [asyncio.create_task(call(middleware, "atacante")) for _ in range(100)]
    await asyncio.sleep(0.02)
    legit = asyncio.create_task(call(middleware, "bot"))
    await asyncio.sleep(0.02)

    assert not legit.done()
    gate.release.set()
    assert (await legit).status == 200
    await asyncio.gather(*flood)


async def test_slots_are_returned_when_requests_finish_or_fail():
    async def failing(scope, receive, send):
        raise RuntimeError("boom")

    middleware = InflightLimitMiddleware(failing, per_client=1)

    for _ in range(5):
        with pytest.raises(RuntimeError):
            await call(middleware, "x")

    assert middleware._active == {}


async def test_health_checks_are_never_throttled():
    gate = Gate()
    gate.release.set()
    middleware = InflightLimitMiddleware(gate.app, per_client=1)
    blocker = Gate()
    holder = InflightLimitMiddleware(blocker.app, per_client=1)
    task = asyncio.create_task(call(holder, "c"))
    await asyncio.sleep(0.01)

    result = await call(holder, "c", "/health")

    blocker.release.set()
    await task
    assert result.status == 200
    assert middleware.per_client == 1


async def test_zero_disables_the_limit():
    gate = Gate()
    middleware = InflightLimitMiddleware(gate.app, per_client=0)
    tasks = [asyncio.create_task(call(middleware, "x")) for _ in range(30)]
    await asyncio.sleep(0.02)
    gate.release.set()
    await asyncio.gather(*tasks)

    assert gate.peak == 30
