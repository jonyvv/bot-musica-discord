from bot.application.clock import PlaybackClock
from bot.application.registry import SessionRegistry


class FakeTime:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


def test_clock_counts_elapsed_time():
    time = FakeTime()
    clock = PlaybackClock(time)
    clock.start()
    time.now += 30

    assert clock.elapsed == 30


def test_clock_excludes_paused_time():
    time = FakeTime()
    clock = PlaybackClock(time)
    clock.start()
    time.now += 10
    clock.pause()
    time.now += 500
    clock.resume()
    time.now += 5

    assert clock.elapsed == 15


def test_clock_stop_resets_to_zero():
    time = FakeTime()
    clock = PlaybackClock(time)
    clock.start()
    time.now += 10
    clock.stop()

    assert clock.elapsed == 0


def test_registry_creates_one_session_per_guild():
    created = []

    def factory(guild_id, on_closed):
        created.append(guild_id)
        return object()

    registry = SessionRegistry(factory)

    assert registry.get_or_create(1) is registry.get_or_create(1)
    assert registry.get_or_create(2) is not registry.get_or_create(1)
    assert created == [1, 2]


def test_registry_discard_allows_recreation():
    registry = SessionRegistry(lambda guild_id, on_closed: object())
    first = registry.get_or_create(1)

    registry.discard(1)

    assert registry.get(1) is None
    assert registry.get_or_create(1) is not first


def test_registry_hands_discard_to_sessions():
    handed = []
    registry = SessionRegistry(lambda guild_id, on_closed: handed.append(on_closed) or object())

    registry.get_or_create(7)
    handed[0](7)

    assert registry.get(7) is None
