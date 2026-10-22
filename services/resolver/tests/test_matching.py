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


def test_parody_one_second_closer_in_duration_does_not_beat_the_original(make_track):
    official = make_track(
        "Luck Ra || BZRP Music Sessions #61/66", 173, "official", artist="Bizarrap"
    )
    parody = make_track(
        "PARODIA LUCK RA || BZRP - Kino Frizzarap", 172, "parody", artist="Kino Frizza"
    )
    query = "Bizarrap - Luck Ra: Bzrp Music Sessions, Vol. 61/66"

    assert pick_best([parody, official], 171, query) is official
    assert pick_best([official, parody], 171, query) is official


def test_real_search_results_for_the_misclassified_song(make_track):
    candidates = [
        make_track("Luck Ra || BZRP Music Sessions #61/66", 173, "1", artist="Bizarrap"),
        make_track("PARODIA LUCK RA || BZRP - Kino Frizzarap", 172, "2", artist="Kino Frizza"),
        make_track("Luck Ra || BZRP Music Sessions #61 (Instrumental)", 171, "4", artist="Zetta"),
        make_track("Luck Ra: Bzrp Music Sessions Vol. 61 | Cover", 181, "5", artist="Kenneth"),
    ]

    best = pick_best(candidates, 171, "Bizarrap - Luck Ra: Bzrp Music Sessions, Vol. 61/66")

    assert best.webpage_url == "1"


def test_official_channel_beats_a_better_ranked_fan_upload(make_track):
    fan = make_track("Song", 200, "fan", artist="Random Channel")
    official = make_track("Song", 200, "official", artist="Artist")

    assert pick_best([fan, official], 200, "Artist - Song") is official


def test_topic_channels_count_as_the_artist(make_track):
    fan = make_track("Song", 200, "fan", artist="Random Channel")
    topic = make_track("Song", 200, "topic", artist="Artist - Topic")

    assert pick_best([fan, topic], 200, "Artist - Song") is topic


def test_durations_within_a_few_seconds_defer_to_search_order(make_track):
    first = make_track("Song", 203, "first", artist="Someone")
    second = make_track("Song", 200, "second", artist="Someone")

    assert pick_best([first, second], 200, "x - song") is first


def test_a_clearly_closer_duration_still_wins_outside_the_equivalence_window(make_track):
    far = make_track("Song", 190, "far", artist="Someone")
    close = make_track("Song", 200, "close", artist="Someone")

    assert pick_best([far, close], 200, "x - song") is close
