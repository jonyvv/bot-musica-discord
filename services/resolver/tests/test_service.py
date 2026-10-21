import pytest

from resolver.application.service import ResolverService
from resolver.domain.errors import TrackNotFoundError, UnsupportedInputError
from resolver.domain.models import CollectionKind, Resolution, Source, StreamInfo


class FakeExtractor:
    def __init__(self, make_track):
        self.make_track = make_track
        self.search_results = []
        self.streamed = []
        self.searched = []

    async def video(self, url):
        return self.make_track("Video", url=url)

    async def playlist(self, url, limit):
        tracks = tuple(self.make_track(f"T{i}", url=f"u{i}") for i in range(limit))
        return Resolution(CollectionKind.PLAYLIST, "List", tracks, truncated=True)

    async def search(self, query, count):
        self.searched.append(query)
        return self.search_results

    async def stream(self, url):
        self.streamed.append(url)
        return StreamInfo(url=f"audio:{url}", headers={}, expires_at=None, webpage_url=url)


class FakeSpotify:
    def __init__(self, make_track):
        self.make_track = make_track

    async def track(self, ref):
        return self.make_track(
            "Spot", 180, url=None, source=Source.SPOTIFY, search_query="A - Spot"
        )

    async def album(self, ref, limit):
        return Resolution(CollectionKind.ALBUM, "Album", (await self.track(ref),))

    async def playlist(self, ref, limit):
        return Resolution(CollectionKind.PLAYLIST, "Mix", (await self.track(ref),))


@pytest.fixture
def extractor(make_track):
    return FakeExtractor(make_track)


@pytest.fixture
def service(extractor, make_track):
    return ResolverService(extractor, FakeSpotify(make_track), max_playlist_size=3)


async def test_resolves_youtube_video_to_single_track(service):
    result = await service.resolve("https://youtu.be/abc")

    assert result.kind == CollectionKind.TRACK
    assert [t.title for t in result.tracks] == ["Video"]


async def test_youtube_playlist_uses_configured_limit(service):
    result = await service.resolve("https://www.youtube.com/playlist?list=PL1")

    assert len(result.tracks) == 3
    assert result.truncated


@pytest.mark.parametrize(
    ("link", "kind"),
    [
        ("https://open.spotify.com/track/abc", CollectionKind.TRACK),
        ("https://open.spotify.com/album/abc", CollectionKind.ALBUM),
        ("https://open.spotify.com/playlist/abc", CollectionKind.PLAYLIST),
    ],
)
async def test_resolves_spotify_links(service, link, kind):
    result = await service.resolve(link)

    assert result.kind == kind
    assert result.tracks[0].source == Source.SPOTIFY


async def test_text_search_returns_best_candidate(service, extractor, make_track):
    extractor.search_results = [make_track("Song (Karaoke)", url="k"), make_track("Song", url="ok")]

    result = await service.resolve("song")

    assert result.kind == CollectionKind.SEARCH
    assert result.tracks[0].webpage_url == "ok"


async def test_text_search_without_results_fails(service):
    with pytest.raises(TrackNotFoundError):
        await service.resolve("nada")


async def test_unsupported_link_fails(service):
    with pytest.raises(UnsupportedInputError):
        await service.resolve("https://example.com/x")


async def test_stream_of_track_with_url_skips_search(service, extractor, make_track):
    stream = await service.stream(make_track(url="direct"))

    assert stream.url == "audio:direct"
    assert extractor.searched == []


async def test_stream_of_spotify_track_matches_by_duration(service, extractor, make_track):
    extractor.search_results = [
        make_track("Song", 400, url="too-long"),
        make_track("Song", 181, url="match"),
    ]
    spotify_track = make_track(
        "Song", 180, url=None, source=Source.SPOTIFY, search_query="A - Song"
    )

    stream = await service.stream(spotify_track)

    assert extractor.searched == ["A - Song"]
    assert stream.webpage_url == "match"


async def test_stream_of_spotify_track_without_match_fails(service, make_track):
    spotify_track = make_track(
        "Song", 180, url=None, source=Source.SPOTIFY, search_query="A - Song"
    )

    with pytest.raises(TrackNotFoundError):
        await service.stream(spotify_track)
