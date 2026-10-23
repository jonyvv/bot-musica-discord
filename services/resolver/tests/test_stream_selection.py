import httpx
import pytest

from resolver.domain.errors import (
    BotDetectedError,
    TrackUnavailableError,
    UpstreamError,
)
from resolver.domain.models import StreamInfo
from resolver.infrastructure.ytdlp_extractor import (
    YtDlpExtractor,
    YtDlpOptions,
    is_trusted_media_url,
    make_probe,
)

PAGE = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
MEDIA = "https://rr1---sn-abc.googlevideo.com/videoplayback?id={}"


class Scripted:
    def __init__(self, outcomes):
        self.outcomes = outcomes
        self.clients_used = []

    async def extract(self, url, **overrides):
        client = overrides["extractor_args"]["youtube"]["player_client"][0]
        self.clients_used.append(client)
        outcome = self.outcomes[client]
        if isinstance(outcome, Exception):
            raise outcome
        return {"url": MEDIA.format(client), "http_headers": {"User-Agent": "UA"}, **outcome}


def extractor(outcomes, playable, clients="tv_simply,web_embedded,web"):
    scripted = Scripted(outcomes)
    probed = []

    async def probe(stream: StreamInfo) -> bool:
        probed.append(stream.url)
        return stream.url.endswith(tuple(playable))

    instance = YtDlpExtractor(YtDlpOptions(player_client=clients), probe=probe)
    instance._extract = scripted.extract
    return instance, scripted, probed


async def test_first_client_is_used_when_its_url_is_readable():
    instance, scripted, probed = extractor({"tv_simply": {}}, playable=["tv_simply"])

    stream = await instance.stream(PAGE)

    assert stream.url.endswith("tv_simply")
    assert scripted.clients_used == ["tv_simply"]
    assert len(probed) == 1


async def test_next_client_is_tried_when_the_url_is_rejected_by_youtube():
    outcomes = {"tv_simply": {}, "web_embedded": {}}
    instance, scripted, _ = extractor(outcomes, playable=["web_embedded"])

    stream = await instance.stream(PAGE)

    assert stream.url.endswith("web_embedded")
    assert scripted.clients_used == ["tv_simply", "web_embedded"]


async def test_next_client_is_tried_when_extraction_itself_fails():
    outcomes = {"tv_simply": UpstreamError("formato"), "web_embedded": {}}
    instance, scripted, _ = extractor(outcomes, playable=["web_embedded"])

    assert (await instance.stream(PAGE)).url.endswith("web_embedded")
    assert scripted.clients_used == ["tv_simply", "web_embedded"]


async def test_gives_up_when_no_client_produces_a_readable_url():
    outcomes = {"tv_simply": {}, "web_embedded": {}, "web": {}}
    instance, scripted, _ = extractor(outcomes, playable=[])

    with pytest.raises(TrackUnavailableError):
        await instance.stream(PAGE)

    assert scripted.clients_used == ["tv_simply", "web_embedded", "web"]


async def test_reports_the_last_extraction_error_when_every_client_fails():
    outcomes = {
        "tv_simply": UpstreamError("uno"),
        "web_embedded": UpstreamError("dos"),
        "web": UpstreamError("tres"),
    }
    instance, _, _ = extractor(outcomes, playable=[])

    with pytest.raises(UpstreamError, match="tres"):
        await instance.stream(PAGE)


async def test_bot_detection_stops_immediately_without_hitting_youtube_again():
    outcomes = {"tv_simply": BotDetectedError("bloqueado"), "web_embedded": {}}
    instance, scripted, _ = extractor(outcomes, playable=["web_embedded"])

    with pytest.raises(BotDetectedError):
        await instance.stream(PAGE)

    assert scripted.clients_used == ["tv_simply"]


async def test_policy_rejections_do_not_fall_through_to_other_clients():
    outcomes = {"tv_simply": {"is_live": True}, "web_embedded": {}}
    instance, scripted, _ = extractor(outcomes, playable=["web_embedded"])

    with pytest.raises(TrackUnavailableError):
        await instance.stream(PAGE)

    assert scripted.clients_used == ["tv_simply"]


async def test_urls_outside_youtube_media_domains_are_never_returned_or_probed():
    scripted = Scripted({"tv_simply": {"url": "http://169.254.169.254/latest/meta-data/"}})
    probed = []

    async def probe(stream):
        probed.append(stream.url)
        return True

    instance = YtDlpExtractor(YtDlpOptions(player_client="tv_simply"), probe=probe)
    instance._extract = scripted.extract

    with pytest.raises(TrackUnavailableError):
        await instance.stream(PAGE)

    assert probed == []


async def test_no_configured_client_falls_back_to_the_ytdlp_default():
    async def extract(url, **overrides):
        assert "extractor_args" not in overrides
        return {"url": MEDIA.format("x")}

    async def probe(stream):
        return True

    instance = YtDlpExtractor(YtDlpOptions(player_client=""), probe=probe)
    instance._extract = extract

    assert (await instance.stream(PAGE)).url.endswith("x")


@pytest.mark.parametrize(
    ("url", "trusted"),
    [
        ("https://rr1---sn-abc.googlevideo.com/videoplayback?id=1", True),
        ("https://manifest.googlevideo.com/api/manifest/hls_playlist", True),
        ("https://www.youtube.com/api/stats", True),
        ("http://rr1---sn-abc.googlevideo.com/videoplayback", False),
        ("https://googlevideo.com.evil.example/x", False),
        ("https://evil.example/googlevideo.com", False),
        ("https://notgooglevideo.com/x", False),
        ("http://169.254.169.254/latest/meta-data/", False),
        ("file:///etc/passwd", False),
        ("", False),
    ],
)
def test_trusted_media_hosts(url, trusted):
    assert is_trusted_media_url(url) is trusted


@pytest.mark.parametrize(
    ("status", "expected"), [(200, True), (206, True), (403, False), (404, False), (302, False)]
)
async def test_probe_accepts_only_readable_status_codes(status, expected):
    seen = {}

    def handler(request):
        seen["range"] = request.headers.get("range")
        seen["ua"] = request.headers.get("user-agent")
        return httpx.Response(status)

    probe = make_probe(httpx.MockTransport(handler))
    stream = StreamInfo(
        url=MEDIA.format("x"), headers={"User-Agent": "UA"}, expires_at=None, webpage_url="w"
    )

    assert await probe(stream) is expected
    assert seen == {"range": "bytes=0-", "ua": "UA"}


async def test_probe_treats_network_failures_as_unreadable():
    def handler(request):
        raise httpx.ConnectError("sin red")

    probe = make_probe(httpx.MockTransport(handler))
    stream = StreamInfo(url=MEDIA.format("x"), headers={}, expires_at=None, webpage_url="w")

    assert await probe(stream) is False
