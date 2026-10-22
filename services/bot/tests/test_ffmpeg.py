import shlex

import pytest

from bot.infrastructure.ffmpeg import PROTOCOLS, RECONNECT, before_options, is_remote_url

EXPECTED_BASE = shlex.split(f"{PROTOCOLS} {RECONNECT}")


def test_without_headers_only_network_and_reconnect_options():
    assert shlex.split(before_options({})) == EXPECTED_BASE


def test_local_protocols_are_never_allowed():
    allowed = PROTOCOLS.split()[-1].split(",")

    assert not {"file", "concat", "subfile", "data", "pipe", "ftp", "gopher"} & set(allowed)


def test_headers_are_a_single_quoted_argument_with_crlf_separators():
    tokens = shlex.split(before_options({"User-Agent": "UA", "Accept": "*/*"}))

    assert tokens == [*EXPECTED_BASE, "-headers", "User-Agent: UA\r\nAccept: */*\r\n"]


@pytest.mark.parametrize(
    "value",
    [
        'a" -i /etc/passwd "b',
        "a\r\n-i file:///etc/passwd",
        "a\\" + '" -f lavfi -i anullsrc',
        '"; rm -rf / #',
        "$(touch /tmp/pwned)",
        "`touch /tmp/pwned`",
    ],
)
def test_hostile_header_values_cannot_inject_extra_arguments(value):
    tokens = shlex.split(before_options({"X-Test": value}))

    assert len(tokens) == len(EXPECTED_BASE) + 2
    assert tokens[-2] == "-headers"
    assert "-i" not in tokens[:-1]


def test_hostile_header_names_cannot_inject_extra_arguments():
    tokens = shlex.split(before_options({'X" -i /etc/passwd "': "v"}))

    assert len(tokens) == len(EXPECTED_BASE) + 2


@pytest.mark.parametrize(
    "url",
    ["https://r1.googlevideo.com/videoplayback?id=1", "http://example.com/a.m3u8"],
)
def test_remote_urls_are_accepted(url):
    assert is_remote_url(url)


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "concat:file:///etc/passwd|https://x",
        "subfile,,start,0,end,0,,:/etc/passwd",
        "data:audio/mp3;base64,AAAA",
        "pipe:0",
        "-f lavfi -i anullsrc",
        "https://x/a b",
        "https://x/a\nb",
        "rtmp://x/live",
        "ftp://x/a",
        "",
    ],
)
def test_non_http_or_malformed_urls_are_rejected(url):
    assert not is_remote_url(url)
