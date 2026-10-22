import pytest

from resolver.application.intent import InputKind, classify
from resolver.domain.errors import UnsupportedInputError

VIDEO = "dQw4w9WgXcQ"
CANONICAL_VIDEO = f"https://www.youtube.com/watch?v={VIDEO}"
PLAYLIST = "PLFgquLnL59alCl_2TQvOiD5Vgm1hCaGSI"
CANONICAL_PLAYLIST = f"https://www.youtube.com/playlist?list={PLAYLIST}"


@pytest.mark.parametrize(
    ("text", "kind", "ref"),
    [
        (f"https://www.youtube.com/watch?v={VIDEO}", InputKind.YOUTUBE_VIDEO, CANONICAL_VIDEO),
        (f"https://youtu.be/{VIDEO}?t=10", InputKind.YOUTUBE_VIDEO, CANONICAL_VIDEO),
        (f"https://music.youtube.com/watch?v={VIDEO}", InputKind.YOUTUBE_VIDEO, CANONICAL_VIDEO),
        (
            f"https://m.youtube.com/watch?v={VIDEO}&feature=share",
            InputKind.YOUTUBE_VIDEO,
            CANONICAL_VIDEO,
        ),
        (f"https://www.youtube.com/shorts/{VIDEO}", InputKind.YOUTUBE_VIDEO, CANONICAL_VIDEO),
        (f"https://www.youtube.com/live/{VIDEO}?si=x", InputKind.YOUTUBE_VIDEO, CANONICAL_VIDEO),
        (f"HTTPS://WWW.YOUTUBE.COM/watch?v={VIDEO}", InputKind.YOUTUBE_VIDEO, CANONICAL_VIDEO),
        (
            f"https://www.youtube.com/playlist?list={PLAYLIST}&si=zzz",
            InputKind.YOUTUBE_PLAYLIST,
            CANONICAL_PLAYLIST,
        ),
        (
            f"https://music.youtube.com/playlist?list={PLAYLIST}",
            InputKind.YOUTUBE_PLAYLIST,
            CANONICAL_PLAYLIST,
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
            "https://open.spotify.com/playlist/37i9dQZF1DXcBWIGoYBM5M/",
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
    assert intent.ref == ref


def test_video_inside_playlist_is_treated_as_video_only():
    intent = classify(f"https://www.youtube.com/watch?v={VIDEO}&list={PLAYLIST}&index=3")

    assert intent.kind == InputKind.YOUTUBE_VIDEO
    assert intent.ref == CANONICAL_VIDEO


def test_reference_never_contains_user_controlled_extras():
    intent = classify(
        f"https://www.youtube.com/watch?v={VIDEO}&x=%0a;rm%20-rf%20/&redirect=http://evil"
    )

    assert intent.ref == CANONICAL_VIDEO


@pytest.mark.parametrize(
    "text",
    [
        "",
        "   ",
        "https://example.com/video",
        "https://www.youtube.com/@canal",
        "https://www.youtube.com/watch",
        "https://www.youtube.com/watch?v=corto",
        f"https://www.youtube.com/watch?v={VIDEO}x",
        f"https://www.youtube.com/redirect?v={VIDEO}&q=http://169.254.169.254",
        f"https://user:pass@www.youtube.com/watch?v={VIDEO}",
        f"https://www.youtube.com:8443/watch?v={VIDEO}",
        "https://www.youtube.com/playlist?list=corta",
        "https://open.spotify.com/artist/0TnOYISbd1XYRBk9myaseg",
        "https://open.spotify.com/track/../../etc/passwd",
    ],
)
def test_classify_rejects_unsupported_inputs(text):
    with pytest.raises(UnsupportedInputError):
        classify(text)
