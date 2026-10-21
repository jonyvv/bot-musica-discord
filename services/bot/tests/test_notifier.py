from types import SimpleNamespace

import discord
import pytest

from bot.infrastructure.notifier import DiscordNotifier


class FakeTextChannel(discord.abc.Messageable):
    def __init__(self, error=None):
        self.sent = []
        self._error = error

    async def _get_channel(self):
        return self

    async def send(self, text, **kwargs):
        if self._error:
            raise self._error
        self.sent.append((text, kwargs))


def notifier_with(channel):
    bot = SimpleNamespace(get_channel=lambda channel_id: channel if channel_id == 9 else None)
    return DiscordNotifier(bot)


async def test_sends_text_without_mentions():
    channel = FakeTextChannel()
    notifier = notifier_with(channel)
    notifier.bind(9)

    await notifier.send("hola @everyone")

    text, kwargs = channel.sent[0]
    assert text == "hola @everyone"
    assert kwargs["allowed_mentions"].everyone is False
    assert kwargs["allowed_mentions"].users is False


async def test_without_bound_channel_does_nothing():
    channel = FakeTextChannel()

    await notifier_with(channel).send("hola")

    assert channel.sent == []


async def test_unknown_channel_does_nothing():
    notifier = notifier_with(FakeTextChannel())
    notifier.bind(404)

    await notifier.send("hola")


async def test_http_failure_is_swallowed():
    response = SimpleNamespace(status=403, reason="Forbidden")
    channel = FakeTextChannel(error=discord.HTTPException(response, "no permission"))
    notifier = notifier_with(channel)
    notifier.bind(9)

    await notifier.send("hola")


@pytest.mark.parametrize("channel_id", [0, None])
async def test_falsy_channel_ids_are_ignored(channel_id):
    notifier = notifier_with(FakeTextChannel())
    notifier._channel_id = channel_id

    await notifier.send("hola")
