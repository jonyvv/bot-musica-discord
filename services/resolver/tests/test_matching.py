from resolver.application.matching import pick_best


def test_prefers_closest_duration(make_track):
    far = make_track("Song", 210, url="far")
    close = make_track("Song", 201, url="close")

    assert pick_best([far, close], 200, "artist - song") is close


def test_rejects_candidates_outside_tolerance(make_track):
    assert pick_best([make_track("Song", 260)], 200, "artist - song") is None


def test_avoids_unwanted_versions_when_not_requested(make_track):
    remix = make_track("Song (Remix)", 200, url="remix")
    original = make_track("Song", 200, url="original")

    assert pick_best([remix, original], 200, "artist - song") is original


def test_accepts_unwanted_version_when_requested(make_track):
    remix = make_track("Song (Remix)", 200, url="remix")

    assert pick_best([remix], 200, "artist - song remix") is remix


def test_skips_live_streams(make_track):
    live = make_track("Song", 200, is_live=True)

    assert pick_best([live], 200, "song") is None


def test_ignores_duration_when_none_expected(make_track):
    first = make_track("Song", 999, url="first")

    assert pick_best([first], None, "song") is first


def test_candidate_without_duration_is_rejected_when_one_is_expected(make_track):
    assert pick_best([make_track("Song", None)], 200, "song") is None


def test_keeps_search_order_on_ties(make_track):
    first = make_track("Song", 200, url="first")
    second = make_track("Song", 200, url="second")

    assert pick_best([first, second], 200, "song") is first
