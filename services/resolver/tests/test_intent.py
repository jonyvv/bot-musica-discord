import pytest

from resolver.application.intent import InputKind, classify
from resolver.domain.errors import UnsupportedInputError


@pytest.mark.parametrize(
    ("text", "kind", "ref"),
    [
        ("https://www.youtube.com/watch?v=dQw4w9WgXcQ", InputKind.YOUTUBE_VIDEO, None),
        ("https://youtu.be/dQw4w9WgXcQ?t=10", InputKind.YOUTUBE_VIDEO, None),
        ("https://music.youtube.com/watch?v=dQw4w9WgXcQ", InputKind.YOUTUBE_VIDEO, None),
        ("https://www.youtube.com/shorts/abc123", InputKind.YOUTUBE_VIDEO, None),
        (
            "https://www.youtube.com/playlist?list=PL123&si=zzz",
            InputKind.YOUTUBE_PLAYLIST,
            "https://www.youtube.com/playlist?list=PL123",
        ),
        (
            "https://music.youtube.com/playlist?list=OLAK5",
            InputKind.YOUTUBE_PLAYLIST,
            "https://www.youtube.com/playlist?list=OLAK5",
        ),
        (
            "https://open.spotify.com/track/4cOdK2wGLETKBW3PvgPWqT?si=x",
            InputKind.SPOTIFY_TRACK,
            "4cOdK2wGLETKBW3PvgPWqT",
        ),
        (
            "https://open.spotify.com/intl-es/album/4aawyAB9vmqN3uQ7FjRGTy",
            InputKind.SPOTIFY_ALBUM,
            "4aawyAB9vmqN3uQ7FjRGTy",
        ),
        (
            "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M",
            InputKind.SPOTIFY_PLAYLIST,
            "37i9dQZF1DXcBWIGoYBM5M",
        ),
        ("spotify:track:4cOdK2wGLETKBW3PvgPWqT", InputKind.SPOTIFY_TRACK, "4cOdK2wGLETKBW3PvgPWqT"),
        ("dua lipa levitating", InputKind.SEARCH, "dua lipa levitating"),
        ("  mix de rock  ", InputKind.SEARCH, "mix de rock"),
    ],
)
def test_classify_known_inputs(text, kind, ref):
    intent = classify(text)

    assert intent.kind == kind
    assert intent.ref == (ref or text)


def test_video_inside_playlist_is_treated_as_video_only():
    intent = classify("https://www.youtube.com/watch?v=abc&list=PL123")

    assert intent.kind == InputKind.YOUTUBE_VIDEO


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "https://example.com/video",
        "https://www.youtube.com/@canal",
        "https://open.spotify.com/artist/0TnOYISbd1XYRBk9myaseg",
    ],
)
def test_classify_rejects_unsupported_inputs(text):
    with pytest.raises(UnsupportedInputError):
        classify(text)
