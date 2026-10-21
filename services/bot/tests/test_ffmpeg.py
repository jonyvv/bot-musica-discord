from bot.infrastructure.ffmpeg import RECONNECT, before_options


def test_without_headers_only_reconnect_options():
    assert before_options({}) == RECONNECT


def test_headers_are_joined_with_crlf_inside_quotes():
    result = before_options({"User-Agent": "UA", "Accept": "*/*"})

    assert result == f'{RECONNECT} -headers "User-Agent: UA\r\nAccept: */*\r\n"'


def test_dangerous_characters_are_stripped():
    result = before_options({"X": 'a"b\\c\r\nd'})

    assert result.endswith('-headers "X: abcd\r\n"')
    assert result.count('"') == 2
