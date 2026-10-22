import json

import httpx
import pytest

from resolver.domain.errors import SpotifyUnavailableError, UpstreamError
from resolver.domain.models import CollectionKind, Source
from resolver.infrastructure.spotify_embed import SpotifyEmbedCatalog


def page(entity):
    data = {"props": {"pageProps": {"state": {"data": {"entity": entity}}}}}
    script = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'
    return f"<html>{script}</html>"


def catalog_for(handler):
    return SpotifyEmbedCatalog(httpx.AsyncClient(transport=httpx.MockTransport(handler)))


def respond_with(html, status=200):
    return catalog_for(lambda request: httpx.Response(status, text=html))


async def test_track_metadata():
    entity = {
        "name": "Never Gonna Give You Up",
        "duration": 213573,
        "artists": [{"name": "Rick Astley"}],
    }

    track = await respond_with(page(entity)).track("abc")

    assert track.title == "Never Gonna Give You Up"
    assert track.artist == "Rick Astley"
    assert track.duration_seconds == 214
    assert track.source == Source.SPOTIFY
    assert track.webpage_url is None
    assert track.search_query == "Rick Astley - Never Gonna Give You Up"


async def test_playlist_cleans_artist_separators_and_applies_limit():
    items = [
        {"title": f"Song {i}", "subtitle": "Olivia Rodrigo, Chappell Roan", "duration": 200000}
        for i in range(5)
    ]

    result = await respond_with(page({"name": "Mix", "trackList": items})).playlist("abc", 3)

    assert result.kind == CollectionKind.PLAYLIST
    assert result.title == "Mix"
    assert len(result.tracks) == 3
    assert result.truncated
    assert result.tracks[0].artist == "Olivia Rodrigo, Chappell Roan"
    assert result.tracks[0].search_query == "Olivia Rodrigo - Song 0"


async def test_album_kind():
    entity = {"name": "Album", "trackList": [{"title": "A", "subtitle": "X", "duration": 1000}]}

    result = await respond_with(page(entity)).album("abc", 10)

    assert result.kind == CollectionKind.ALBUM
    assert not result.truncated


async def test_empty_collection_is_reported_as_unavailable():
    with pytest.raises(SpotifyUnavailableError):
        await respond_with(page({"name": "Vacia", "trackList": []})).playlist("abc", 10)


async def test_missing_content_is_reported_as_unavailable():
    with pytest.raises(SpotifyUnavailableError):
        await respond_with("", status=404).track("abc")


async def test_private_playlist_arrives_as_http_200_with_404_inside_the_page():
    data = {"props": {"pageProps": {"status": 404, "title": "Page not found"}}}
    script = f'<script id="__NEXT_DATA__" type="application/json">{json.dumps(data)}</script>'

    with pytest.raises(SpotifyUnavailableError) as caught:
        await respond_with(f"<html>{script}</html>", status=200).playlist("abc", 500)

    assert "pública" in caught.value.message


async def test_hitting_the_embed_cap_flags_the_list_as_possibly_incomplete():
    items = [{"title": f"S{i}", "subtitle": "A", "duration": 1000} for i in range(100)]

    result = await respond_with(page({"name": "Grande", "trackList": items})).playlist("abc", 500)

    assert len(result.tracks) == 100
    assert result.truncated


async def test_list_below_the_cap_is_not_flagged():
    items = [{"title": f"S{i}", "subtitle": "A", "duration": 1000} for i in range(99)]

    result = await respond_with(page({"name": "Chica", "trackList": items})).playlist("abc", 500)

    assert not result.truncated


async def test_changed_page_format_is_reported_as_upstream_error():
    with pytest.raises(UpstreamError):
        await respond_with("<html>nada</html>").track("abc")


async def test_unexpected_json_shape_is_reported_as_upstream_error():
    html = '<script id="__NEXT_DATA__" type="application/json">{"props": {}}</script>'

    with pytest.raises(UpstreamError):
        await respond_with(html).track("abc")


async def test_network_failure_is_reported_as_upstream_error():
    def broken(request):
        raise httpx.ConnectError("sin red")

    with pytest.raises(UpstreamError):
        await catalog_for(broken).track("abc")
