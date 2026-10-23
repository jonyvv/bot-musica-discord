import pytest

from resolver.domain.errors import (
    BotDetectedError,
    TrackNotFoundError,
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
    track = _to_track({"id": "abcdefghijk", "title": "T", "duration": 61.7, "uploader": "Chan"})

    assert track.webpage_url == "https://www.youtube.com/watch?v=abcdefghijk"
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


def test_params_apply_configuration(tmp_path):
    cookies = tmp_path / "c.txt"
    cookies.write_text("# cookies")
    options = YtDlpOptions(
        js_runtime="node",
        player_client="tv, web_safari",
        force_ipv4=True,
        cookies_file=str(cookies),
    )

    params = YtDlpExtractor(options)._params({"format": "x"})

    assert params["js_runtimes"] == {"node": {}}
    assert params["source_address"] == "0.0.0.0"
    assert params["cookiefile"] == str(cookies)
    assert params["extractor_args"] == {"youtube": {"player_client": ["tv", "web_safari"]}}
    assert params["format"] == "x"


def test_params_omit_optional_settings_when_empty():
    params = YtDlpExtractor(YtDlpOptions(force_ipv4=False))._params({})

    assert not {"source_address", "cookiefile", "extractor_args"} & params.keys()


def test_missing_cookies_file_is_ignored_and_warned_once(tmp_path, caplog):
    extractor = YtDlpExtractor(YtDlpOptions(cookies_file=str(tmp_path / "nope" / "c.txt")))

    first = extractor._params({})
    second = extractor._params({})

    assert "cookiefile" not in first
    assert "cookiefile" not in second
    assert caplog.text.count("no existe") == 1


class FakeYoutubeDL:
    def __init__(self, params, close_error=None):
        self.close_error = close_error
        self.closed = False

    def extract_info(self, target, download=False):
        return {"title": "T", "id": "x"}

    def sanitize_info(self, info):
        return info

    def close(self):
        self.closed = True
        if self.close_error:
            raise self.close_error


def test_failure_saving_cookies_does_not_lose_the_result(monkeypatch):
    fake = FakeYoutubeDL({}, close_error=PermissionError("solo lectura"))
    monkeypatch.setattr("resolver.infrastructure.ytdlp_extractor.YoutubeDL", lambda params: fake)

    info = YtDlpExtractor(YtDlpOptions())._extract_sync("x", {})

    assert info["title"] == "T"
    assert fake.closed


def test_ydl_is_closed_even_when_extraction_fails(monkeypatch):
    fake = FakeYoutubeDL({})
    fake.extract_info = lambda target, download=False: None
    monkeypatch.setattr("resolver.infrastructure.ytdlp_extractor.YoutubeDL", lambda params: fake)

    with pytest.raises(TrackNotFoundError):
        YtDlpExtractor(YtDlpOptions())._extract_sync("x", {})

    assert fake.closed
