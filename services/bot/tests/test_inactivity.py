import asyncio

import pytest

from bot.application.inactivity import (
    EMPTY_MESSAGE,
    IDLE_MESSAGE,
    PAUSE_MESSAGE,
    InactivityPolicy,
    Timeouts,
)
from bot.application.session import GuildSession, SessionSettings
from bot.application.timers import TimerRegistry

CHANNEL = 10


class ManualSleeper:
    def __init__(self):
        self.now = 0.0
        self.waiters = []

    async def __call__(self, delay):
        future = asyncio.get_running_loop().create_future()
        self.waiters.append((self.now + delay, future))
        await future

    async def settle(self):
        for _ in range(5):
            await asyncio.sleep(0)

    async def advance(self, seconds):
        await self.settle()
        self.now += seconds
        for deadline, future in list(self.waiters):
            if deadline <= self.now and not future.done():
                future.set_result(None)
        await self.settle()


@pytest.fixture
def clock():
    return ManualSleeper()


@pytest.fixture
def timers(clock):
    return TimerRegistry(sleep=clock)


@pytest.fixture
def make_session(resolver, voice, notifier, timers, closed_guilds):
    def factory(timeouts=None):
        timeouts = timeouts or Timeouts(idle=300, pause=600, empty=120)
        return GuildSession(
            guild_id=1,
            resolver=resolver,
            voice=voice,
            notifier=notifier,
            settings=SessionSettings(default_volume=50, max_queue_size=50),
            activity_factory=lambda close: InactivityPolicy(timers, timeouts, close),
            on_closed=closed_guilds.append,
        )

    return factory


async def start_playing(session, resolver, resolve_to, *titles):
    resolve_to(resolver, *titles)
    await session.enqueue("q", 1, CHANNEL)


async def test_disconnects_after_idle_timeout(
    make_session, resolver, resolve_to, voice, notifier, clock, closed_guilds
):
    session = make_session()
    await start_playing(session, resolver, resolve_to, "a")
    await voice.finish()

    await clock.advance(299)
    assert voice.connected

    await clock.advance(2)
    assert not voice.connected
    assert notifier.messages == [IDLE_MESSAGE]
    assert closed_guilds == [1]


async def test_new_song_cancels_pending_idle_disconnect(
    make_session, resolver, resolve_to, voice, clock
):
    session = make_session()
    await start_playing(session, resolver, resolve_to, "a")
    await voice.finish()
    await clock.advance(290)

    await start_playing(session, resolver, resolve_to, "b")
    await clock.advance(500)

    assert voice.connected


async def test_no_idle_timer_while_music_is_playing(
    make_session, resolver, resolve_to, voice, clock, timers
):
    session = make_session()
    await start_playing(session, resolver, resolve_to, "a")

    await clock.advance(10_000)

    assert voice.connected
    assert timers.active == frozenset()


async def test_disconnects_when_channel_is_empty_even_while_playing(
    make_session, resolver, resolve_to, voice, notifier, clock
):
    session = make_session()
    await start_playing(session, resolver, resolve_to, "a")

    session.channel_emptied()
    await clock.advance(121)

    assert not voice.connected
    assert notifier.messages == [EMPTY_MESSAGE]


async def test_someone_returning_cancels_empty_channel_disconnect(
    make_session, resolver, resolve_to, voice, clock
):
    session = make_session()
    await start_playing(session, resolver, resolve_to, "a")
    session.channel_emptied()
    await clock.advance(100)

    session.channel_occupied()
    await clock.advance(500)

    assert voice.connected


async def test_disconnects_after_long_pause(
    make_session, resolver, resolve_to, voice, notifier, clock
):
    session = make_session()
    await start_playing(session, resolver, resolve_to, "a")

    session.pause()
    await clock.advance(599)
    assert voice.connected

    await clock.advance(2)
    assert not voice.connected
    assert notifier.messages == [PAUSE_MESSAGE]


async def test_resuming_cancels_pause_disconnect(make_session, resolver, resolve_to, voice, clock):
    session = make_session()
    await start_playing(session, resolver, resolve_to, "a")
    session.pause()
    await clock.advance(500)

    session.resume()
    await clock.advance(5_000)

    assert voice.connected


async def test_zero_timeout_disables_the_rule(make_session, resolver, resolve_to, voice, clock):
    session = make_session(Timeouts(idle=0, pause=0, empty=0))
    await start_playing(session, resolver, resolve_to, "a")
    session.channel_emptied()
    session.pause()
    session.resume()
    await voice.finish()

    await clock.advance(100_000)

    assert voice.connected


async def test_closing_session_leaves_no_timers_behind(
    make_session, resolver, resolve_to, voice, clock, timers
):
    session = make_session()
    await start_playing(session, resolver, resolve_to, "a")
    await voice.finish()
    session.channel_emptied()
    assert timers.active == {"idle", "empty"}

    await session.close()

    assert timers.active == frozenset()
    await clock.advance(100_000)
    assert voice.disconnects == 1


async def test_stop_arms_idle_disconnect(make_session, resolver, resolve_to, voice, clock):
    session = make_session()
    await start_playing(session, resolver, resolve_to, "a", "b")

    await session.stop()
    await clock.advance(301)

    assert not voice.connected


async def test_restarting_a_timer_replaces_the_previous_one(timers, clock):
    fired = []

    async def callback():
        fired.append(clock.now)

    timers.start("x", 10, callback)
    await clock.advance(5)
    timers.start("x", 10, callback)
    await clock.advance(7)
    assert fired == []

    await clock.advance(5)
    assert fired == [17]
