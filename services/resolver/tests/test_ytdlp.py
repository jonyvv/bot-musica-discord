import pytest

from resolver.domain.errors import (
    BotDetectedError,
    TrackUnavailableError,
    UnsupportedInputError,
    UpstreamError,
)
from resolver.infrastructure.ytdlp_errors import translate_error
from resolver.infrastructure.ytdlp_extractor import (
    YtDlpExtractor,
    YtDlpOptions,
    _entries_to_tracks,
    _expiry,
    _to_track,
)


@pytest.mark.parametrize(
    ("message", "expected"),
    [
        ("ERROR: [youtube] x: Sign in to confirm you're not a bot", BotDetectedError),
        ("ERROR: Video unavailable. This video is private", TrackUnavailableError),
        ("ERROR: [youtube] abc: This video is unavailable", TrackUnavailableError),
        ("ERROR: Sign in to confirm your age", TrackUnavailableError),
        ("ERROR: Unsupported URL: https://foo", UnsupportedInputError),
        ("ERROR: algo inesperado", UpstreamError),
    ],
)
def test_translate_error(message, expected):
    assert isinstance(translate_error(message), expected)


def test_translate_error_never_leaks_raw_details_to_users():
    error = translate_error("ERROR: cookies file not found: /data/cookies/secret-account.txt")

    assert "secret-account" not in error.message
    assert "/data" not in error.message


def test_to_track_builds_url_from_id_when_missing():
    track = _to_track({"id": "abc", "title": "T", "duration": 61.7, "uploader": "Chan"})

    assert track.webpage_url == "https://www.youtube.com/watch?v=abc"
    assert track.duration_seconds == 61
    assert track.artist == "Chan"


def test_to_track_detects_live_streams():
    assert _to_track({"id": "a", "live_status": "is_live"}).is_live


def test_to_track_uses_last_thumbnail():
    entry = {"id": "a", "thumbnails": [{"url": "small"}, {"url": "big"}]}

    assert _to_track(entry).thumbnail_url == "big"


def test_entries_skip_hidden_and_empty_items():
    info = {
        "entries": [
            None,
            {"id": "a", "title": "[Private video]"},
            {"id": "b", "title": "[Deleted video]"},
            {"id": "c", "title": "Ok"},
            {"title": "Sin url ni id"},
        ]
    }

    assert [t.title for t in _entries_to_tracks(info)] == ["Ok"]


@pytest.mark.parametrize(
    ("url", "expected"),
    [
        ("https://x.googlevideo.com/videoplayback?expire=1792574508&id=1", 1792574508),
        ("https://x.googlevideo.com/videoplayback?id=1", None),
        ("https://x.googlevideo.com/videoplayback?expire=abc", None),
    ],
)
def test_expiry(url, expected):
    assert _expiry(url) == expected


def test_params_apply_configuration():
    options = YtDlpOptions(
        js_runtime="node", player_client="tv, web_safari", force_ipv4=True, cookies_file="c.txt"
    )

    params = YtDlpExtractor(options)._params({"format": "x"})

    assert params["js_runtimes"] == {"node": {}}
    assert params["source_address"] == "0.0.0.0"
    assert params["cookiefile"] == "c.txt"
    assert params["extractor_args"] == {"youtube": {"player_client": ["tv", "web_safari"]}}
    assert params["format"] == "x"


def test_params_omit_optional_settings_when_empty():
    params = YtDlpExtractor(YtDlpOptions(force_ipv4=False))._params({})

    assert not {"source_address", "cookiefile", "extractor_args"} & params.keys()
