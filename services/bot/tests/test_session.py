import asyncio

import pytest

from bot.application.session import PlaybackState
from bot.domain.errors import InvalidRequestError, NotPlayingError, VoiceError
from bot.domain.models import LoopMode

CHANNEL = 10


async def play(session, resolver, resolve_to, *titles, requester=7):
    resolve_to(resolver, *titles)
    return await session.enqueue("query", requester, CHANNEL)


async def test_first_enqueue_connects_and_starts_playing(session, resolver, voice, resolve_to):
    result = await play(session, resolver, resolve_to, "a", "b", "c")

    assert voice.connects == [CHANNEL]
    assert voice.played == ["audio:a"]
    assert session.state is PlaybackState.PLAYING
    assert [t.title for t in session.queue.pending] == ["b", "c"]
    assert result.added == 3
    assert result.position == 0


async def test_enqueue_while_playing_appends_without_interrupting(
    session, resolver, voice, resolve_to
):
    await play(session, resolver, resolve_to, "a", "b")

    result = await play(session, resolver, resolve_to, "c")

    assert voice.played == ["audio:a"]
    assert [t.title for t in session.queue.pending] == ["b", "c"]
    assert result.position == 2


async def test_requester_is_stamped_on_tracks(session, resolver, resolve_to):
    await play(session, resolver, resolve_to, "a", requester=42)

    assert session.queue.current.requester_id == 42


async def test_does_not_reconnect_when_already_in_channel(session, resolver, voice, resolve_to):
    await play(session, resolver, resolve_to, "a")
    await play(session, resolver, resolve_to, "b")

    assert voice.connects == [CHANNEL]


async def test_full_queue_rejects_new_tracks(session, resolver, resolve_to):
    await play(session, resolver, resolve_to, "playing")
    await play(session, resolver, resolve_to, "b", "c", "d", "e", "f")

    with pytest.raises(InvalidRequestError):
        await play(session, resolver, resolve_to, "g")


async def test_song_end_advances_to_next(session, resolver, voice, resolve_to):
    await play(session, resolver, resolve_to, "a", "b")

    await voice.finish()

    assert voice.played == ["audio:a", "audio:b"]
    assert session.queue.current.title == "b"


async def test_queue_exhaustion_goes_idle_and_notifies_observer(
    session, resolver, voice, observer, resolve_to
):
    await play(session, resolver, resolve_to, "a")

    await voice.finish()

    assert session.state is PlaybackState.IDLE
    assert session.queue.current is None
    assert observer.events[-1] == "idle"


async def test_playing_event_is_emitted_for_each_song(
    session, resolver, voice, observer, resolve_to
):
    await play(session, resolver, resolve_to, "a", "b")
    await voice.finish()

    assert observer.events == ["playing", "playing"]


async def test_skip_plays_next_and_returns_skipped(session, resolver, voice, resolve_to):
    await play(session, resolver, resolve_to, "a", "b")

    skipped = await session.skip()

    assert skipped.title == "a"
    assert voice.played == ["audio:a", "audio:b"]
    assert voice.stops == 1


async def test_skip_last_song_goes_idle(session, resolver, resolve_to):
    await play(session, resolver, resolve_to, "a")

    await session.skip()

    assert session.state is PlaybackState.IDLE


async def test_skip_ignores_track_loop(session, resolver, voice, resolve_to):
    await play(session, resolver, resolve_to, "a", "b")
    session.loop_mode = LoopMode.TRACK

    await session.skip()

    assert session.queue.current.title == "b"


async def test_callback_from_skipped_song_is_ignored(session, resolver, voice, resolve_to):
    await play(session, resolver, resolve_to, "a", "b", "c")
    stale = voice.on_finished

    await session.skip()
    await stale(None)

    assert session.queue.current.title == "b"
    assert voice.played == ["audio:a", "audio:b"]


async def test_skip_without_current_song_fails(session):
    with pytest.raises(NotPlayingError):
        await session.skip()


async def test_loop_track_replays_same_song(session, resolver, voice, resolve_to):
    await play(session, resolver, resolve_to, "a", "b")
    session.loop_mode = LoopMode.TRACK

    await voice.finish()

    assert voice.played == ["audio:a", "audio:a"]


async def test_loop_queue_cycles_back_to_start(session, resolver, voice, resolve_to):
    await play(session, resolver, resolve_to, "a", "b")
    session.loop_mode = LoopMode.QUEUE

    await voice.finish()
    await voice.finish()

    assert voice.played == ["audio:a", "audio:b", "audio:a"]


async def test_unplayable_song_is_reported_and_skipped(
    session, resolver, voice, notifier, resolve_to
):
    resolver.failing_titles = {"bad"}

    await play(session, resolver, resolve_to, "bad", "good")

    assert voice.played == ["audio:good"]
    assert any("bad" in message for message in notifier.messages)


async def test_failing_song_under_track_loop_does_not_loop_forever(
    session, resolver, voice, resolve_to
):
    resolver.failing_titles = {"bad"}
    session.loop_mode = LoopMode.TRACK

    await play(session, resolver, resolve_to, "bad", "good")

    assert voice.played == ["audio:good"]


async def test_all_songs_failing_leaves_session_idle(session, resolver, resolve_to):
    resolver.failing_titles = {"a", "b"}

    await play(session, resolver, resolve_to, "a", "b")

    assert session.state is PlaybackState.IDLE


async def test_pause_and_resume_update_state_and_observer(
    session, resolver, voice, observer, resolve_to
):
    await play(session, resolver, resolve_to, "a")

    session.pause()
    assert session.state is PlaybackState.PAUSED
    assert voice.paused

    session.resume()
    assert session.state is PlaybackState.PLAYING
    assert not voice.paused
    assert observer.events == ["playing", "paused", "playing"]


async def test_pause_when_nothing_plays_fails(session):
    with pytest.raises(NotPlayingError):
        session.pause()


async def test_resume_when_not_paused_fails(session, resolver, resolve_to):
    await play(session, resolver, resolve_to, "a")

    with pytest.raises(NotPlayingError):
        session.resume()


async def test_stop_clears_queue_and_goes_idle(session, resolver, voice, resolve_to):
    await play(session, resolver, resolve_to, "a", "b", "c")

    await session.stop()

    assert session.state is PlaybackState.IDLE
    assert session.queue.current is None
    assert len(session.queue) == 0
    assert voice.connected


async def test_stop_prevents_stale_callback_from_restarting(session, resolver, voice, resolve_to):
    await play(session, resolver, resolve_to, "a", "b")
    stale = voice.on_finished

    await session.stop()
    await stale(None)

    assert voice.played == ["audio:a"]


async def test_volume_persists_into_next_song(session, resolver, voice, resolve_to):
    await play(session, resolver, resolve_to, "a", "b")

    session.set_volume(120)
    await voice.finish()

    assert voice.volumes[-1] == 120


@pytest.mark.parametrize("volume", [-1, 151])
async def test_volume_out_of_range_is_rejected(session, volume):
    with pytest.raises(InvalidRequestError):
        session.set_volume(volume)


async def test_close_releases_everything_and_notifies(
    session, resolver, voice, notifier, observer, closed_guilds, resolve_to
):
    await play(session, resolver, resolve_to, "a", "b")

    await session.close("Adios")

    assert not voice.connected
    assert voice.disconnects == 1
    assert session.queue.current is None
    assert "close" in observer.events
    assert notifier.messages == ["Adios"]
    assert closed_guilds == [1]


async def test_close_is_idempotent(session, voice, closed_guilds):
    await session.close()
    await session.close()

    assert voice.disconnects == 1
    assert closed_guilds == [1]


async def test_close_without_reason_is_silent(session, notifier):
    await session.close()

    assert notifier.messages == []


async def test_callback_after_close_does_nothing(session, resolver, voice, resolve_to):
    await play(session, resolver, resolve_to, "a", "b")
    stale = voice.on_finished

    await session.close()
    await stale(None)

    assert voice.played == ["audio:a"]


async def test_enqueue_after_close_fails(session, resolver, resolve_to):
    await session.close()

    with pytest.raises(VoiceError):
        await play(session, resolver, resolve_to, "a")


async def test_idle_event_after_close_is_not_emitted(
    session, resolver, voice, observer, resolve_to
):
    await play(session, resolver, resolve_to, "a")
    await session.close()
    observer.events.clear()

    await session.stop()

    assert observer.events == []


async def test_concurrent_enqueues_keep_queue_consistent(session, resolver, voice, resolve_to):
    resolve_to(resolver, "a", "b")

    await asyncio.gather(*(session.enqueue("q", 1, CHANNEL) for _ in range(2)))

    assert voice.played == ["audio:a"]
    assert [t.title for t in session.queue.pending] == ["b", "a", "b"]


async def test_channel_events_are_forwarded_to_observer(session, observer):
    session.channel_emptied()
    session.channel_occupied()

    assert observer.events == ["channel_empty", "channel_occupied"]


async def test_text_channel_is_bound_to_notifier(session, notifier):
    session.bind_text_channel(99)

    assert notifier.channel == 99
