import asyncio
from types import SimpleNamespace
from typing import ClassVar

import discord
import pytest

from bot.domain.errors import VoiceError
from bot.domain.models import StreamInfo
from bot.infrastructure.voice import DiscordVoiceGateway

STREAM = StreamInfo(
    url="https://audio", headers={"User-Agent": "UA"}, expires_at=None, webpage_url="w"
)


class FakeAudio(discord.AudioSource):
    created: ClassVar[list] = []

    def __init__(self, url, **kwargs):
        self.url = url
        self.kwargs = kwargs
        FakeAudio.created.append(self)

    def read(self):
        return b""


class FakeClient:
    def __init__(self, channel_id=1, connected=True):
        self.channel = SimpleNamespace(id=channel_id)
        self.connected = connected
        self.source = None
        self.after = None
        self.play_error = None
        self.calls = []

    def is_connected(self):
        return self.connected

    async def move_to(self, channel):
        self.channel = channel
        self.calls.append("move_to")

    async def disconnect(self, force=False):
        self.connected = False
        self.calls.append("disconnect")

    def play(self, source, after=None):
        if self.play_error:
            raise self.play_error
        self.source, self.after = source, after

    def pause(self):
        self.calls.append("pause")

    def resume(self):
        self.calls.append("resume")

    def stop(self):
        self.calls.append("stop")


class FakeChannel:
    def __init__(self, guild, channel_id, error=None):
        self.id = channel_id
        self._guild = guild
        self._error = error

    async def connect(self, self_deaf=False):
        if self._error:
            raise self._error
        self._guild.voice_client = FakeClient(self.id)


@pytest.fixture
def guild():
    return SimpleNamespace(voice_client=None, channels={})


@pytest.fixture
def gateway(guild, monkeypatch):
    guild.get_channel = guild.channels.get
    bot = SimpleNamespace(get_guild=lambda guild_id: guild if guild_id == 5 else None)
    monkeypatch.setattr(discord, "FFmpegPCMAudio", FakeAudio)
    FakeAudio.created.clear()
    return DiscordVoiceGateway(bot, 5)


def attach(guild, client):
    guild.voice_client = client
    return client


async def test_not_connected_without_client(gateway):
    assert not gateway.is_connected
    assert gateway.channel_id is None


async def test_connect_joins_channel_with_self_deaf(gateway, guild):
    guild.channels[10] = FakeChannel(guild, 10)

    await gateway.connect(10)

    assert gateway.is_connected
    assert gateway.channel_id == 10


async def test_connect_moves_when_already_connected_elsewhere(gateway, guild):
    client = attach(guild, FakeClient(channel_id=1))
    guild.channels[10] = FakeChannel(guild, 10)

    await gateway.connect(10)

    assert "move_to" in client.calls
    assert gateway.channel_id == 10


async def test_connect_replaces_stale_disconnected_client(gateway, guild):
    stale = attach(guild, FakeClient(connected=False))
    guild.channels[10] = FakeChannel(guild, 10)

    await gateway.connect(10)

    assert "disconnect" in stale.calls
    assert guild.voice_client is not stale


async def test_connect_to_unknown_channel_fails(gateway):
    with pytest.raises(VoiceError):
        await gateway.connect(404)


@pytest.mark.parametrize("error", [discord.ClientException("x"), TimeoutError()])
async def test_connect_failure_becomes_voice_error(gateway, guild, error):
    guild.channels[10] = FakeChannel(guild, 10, error=error)

    with pytest.raises(VoiceError):
        await gateway.connect(10)


async def test_play_applies_volume_and_ffmpeg_options(gateway, guild):
    client = attach(guild, FakeClient())

    await gateway.play(STREAM, 80, on_finished=lambda error: asyncio.sleep(0))

    assert client.source.volume == 0.8
    audio = FakeAudio.created[0]
    assert audio.url == "https://audio"
    assert "-reconnect 1" in audio.kwargs["before_options"]
    assert "User-Agent: UA" in audio.kwargs["before_options"]
    assert audio.kwargs["options"] == "-vn"


async def test_play_without_connection_fails(gateway):
    with pytest.raises(VoiceError):
        await gateway.play(STREAM, 50, on_finished=lambda error: asyncio.sleep(0))


async def test_play_failure_becomes_voice_error(gateway, guild):
    attach(guild, FakeClient()).play_error = discord.ClientException("no ffmpeg")

    with pytest.raises(VoiceError) as caught:
        await gateway.play(STREAM, 50, on_finished=lambda error: asyncio.sleep(0))

    assert "FFmpeg" in caught.value.user_message


async def test_finish_callback_from_audio_thread_reaches_event_loop(gateway, guild):
    client = attach(guild, FakeClient())
    done = asyncio.Event()
    received = []

    async def on_finished(error):
        received.append(error)
        done.set()

    await gateway.play(STREAM, 50, on_finished)
    await asyncio.to_thread(client.after, None)
    await asyncio.wait_for(done.wait(), 1)

    assert received == [None]


async def test_set_volume_updates_current_source(gateway, guild):
    client = attach(guild, FakeClient())
    await gateway.play(STREAM, 50, on_finished=lambda error: asyncio.sleep(0))

    gateway.set_volume(120)

    assert client.source.volume == 1.2


async def test_set_volume_without_source_is_harmless(gateway, guild):
    attach(guild, FakeClient())

    gateway.set_volume(120)


async def test_pause_resume_stop_delegate_to_client(gateway, guild):
    client = attach(guild, FakeClient())

    gateway.pause()
    gateway.resume()
    gateway.stop()

    assert client.calls == ["pause", "resume", "stop"]


async def test_controls_without_client_do_nothing(gateway):
    gateway.pause()
    gateway.resume()
    gateway.stop()
    await gateway.disconnect()


async def test_disconnect_forces_client_disconnect(gateway, guild):
    client = attach(guild, FakeClient())

    await gateway.disconnect()

    assert client.calls == ["disconnect"]
