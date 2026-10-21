import random

import pytest

from bot.domain.errors import InvalidRequestError
from bot.domain.models import LoopMode
from bot.domain.queue import TrackQueue


@pytest.fixture
def queue():
    return TrackQueue(max_size=3)


def titles(tracks):
    return [t.title for t in tracks]


def test_add_respects_max_size(queue, make_track):
    added = queue.add([make_track(str(i)) for i in range(5)])

    assert added == 3
    assert titles(queue.pending) == ["0", "1", "2"]


def test_add_to_full_queue_adds_nothing(queue, make_track):
    queue.add([make_track(str(i)) for i in range(3)])

    assert queue.add([make_track("extra")]) == 0


def test_advance_moves_through_queue_in_order(queue, make_track):
    queue.add([make_track("a"), make_track("b")])

    assert queue.advance(LoopMode.OFF).title == "a"
    assert queue.advance(LoopMode.OFF).title == "b"
    assert queue.advance(LoopMode.OFF) is None
    assert queue.current is None


def test_loop_track_repeats_current(queue, make_track):
    queue.add([make_track("a"), make_track("b")])
    queue.advance(LoopMode.OFF)

    assert queue.advance(LoopMode.TRACK).title == "a"
    assert titles(queue.pending) == ["b"]


def test_force_ignores_track_loop(queue, make_track):
    queue.add([make_track("a"), make_track("b")])
    queue.advance(LoopMode.OFF)

    assert queue.advance(LoopMode.TRACK, force=True).title == "b"


def test_loop_queue_recycles_finished_tracks(queue, make_track):
    queue.add([make_track("a"), make_track("b")])
    order = [queue.advance(LoopMode.QUEUE).title for _ in range(5)]

    assert order == ["a", "b", "a", "b", "a"]


def test_loop_queue_with_single_track_repeats_it(queue, make_track):
    queue.add([make_track("a")])

    assert [queue.advance(LoopMode.QUEUE).title for _ in range(3)] == ["a", "a", "a"]


def test_remove_by_position(queue, make_track):
    queue.add([make_track("a"), make_track("b"), make_track("c")])

    assert queue.remove(2).title == "b"
    assert titles(queue.pending) == ["a", "c"]


@pytest.mark.parametrize("position", [0, 4, -1])
def test_remove_rejects_invalid_position(queue, make_track, position):
    queue.add([make_track("a"), make_track("b"), make_track("c")])

    with pytest.raises(InvalidRequestError):
        queue.remove(position)


def test_clear_keeps_current_track(queue, make_track):
    queue.add([make_track("a"), make_track("b")])
    queue.advance(LoopMode.OFF)

    assert queue.clear() == 1
    assert queue.current.title == "a"
    assert len(queue) == 0


def test_shuffle_keeps_same_tracks_and_current(queue, make_track):
    queue.add([make_track("a"), make_track("b"), make_track("c")])
    queue.advance(LoopMode.OFF)

    queue.shuffle(random.Random(1))

    assert sorted(titles(queue.pending)) == ["b", "c"]
    assert queue.current.title == "a"


def test_reset_clears_everything(queue, make_track):
    queue.add([make_track("a"), make_track("b")])
    queue.advance(LoopMode.OFF)

    queue.reset()

    assert queue.current is None
    assert len(queue) == 0


def test_pending_seconds_sums_known_durations(queue, make_track):
    queue.add([make_track("a", 100), make_track("b", None), make_track("c", 50)])

    assert queue.pending_seconds == 150
