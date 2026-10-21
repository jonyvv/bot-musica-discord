from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.application.registry import SessionRegistry
from bot.application.session import PlaybackState
from bot.domain.errors import BotError
from bot.domain.models import LoopMode
from bot.main import FFMPEG_HINT, build_bot, ensure_ffmpeg, load_settings
from bot.presentation.bot import MusicBot
from bot.presentation.cogs.events import VoiceEventsCog
from bot.presentation.cogs.playback import PlaybackCog
from bot.presentation.cogs.queue import QueueCog

CHANNEL = 10


def interaction_in(channel_id=CHANNEL, user_id=7):
    channel = SimpleNamespace(
        id=channel_id,
        mention="#voz",
        members=[],
        user_limit=0,
        permissions_for=lambda member: SimpleNamespace(connect=True, speak=True, move_members=True),
    )
    return SimpleNamespace(
        guild=SimpleNamespace(id=1, me=object()),
        user=SimpleNamespace(id=user_id, voice=SimpleNamespace(channel=channel)),
        channel_id=555,
        response=SimpleNamespace(defer=AsyncMock(), send_message=AsyncMock()),
        followup=SimpleNamespace(send=AsyncMock()),
    )


@pytest.fixture
def registry(session):
    created = SessionRegistry(lambda guild_id, on_closed: session)
    created.get_or_create(1)
    return created


@pytest.fixture
def playback(registry):
    return PlaybackCog(registry)


@pytest.fixture
def queue_cog(registry):
    return QueueCog(registry)


async def call(command, cog, interaction, *args):
    await command.callback(cog, interaction, *args)


def said(interaction):
    return interaction.response.send_message.await_args.args[0]


async def test_play_binds_channel_enqueues_and_replies(
    playback, session, resolver, resolve_to, notifier, voice
):
    resolve_to(resolver, "a", "b")
    interaction = interaction_in()

    await call(playback.play, playback, interaction, "mi busqueda")

    interaction.response.defer.assert_awaited_once()
    assert notifier.channel == 555
    assert resolver.queries == ["mi busqueda"]
    assert voice.played == ["audio:a"]
    assert interaction.followup.send.await_args.kwargs["embed"].title.startswith("➕")


async def test_play_requires_voice_channel(playback):
    interaction = interaction_in()
    interaction.user.voice = None

    with pytest.raises(BotError):
        await call(playback.play, playback, interaction, "x")


async def test_skip_replies_with_skipped_title(playback, session, resolver, resolve_to):
    resolve_to(resolver, "a", "b")
    await session.enqueue("q", 7, CHANNEL)

    interaction = interaction_in()
    await call(playback.skip, playback, interaction)

    assert "a" in said(interaction)
    assert session.queue.current.title == "b"


async def test_pause_resume_cycle(playback, session, resolver, resolve_to):
    resolve_to(resolver, "a")
    await session.enqueue("q", 7, CHANNEL)

    await call(playback.pause, playback, interaction_in())
    assert session.state is PlaybackState.PAUSED
    await call(playback.resume, playback, interaction_in())
    assert session.state is PlaybackState.PLAYING


async def test_stop_clears_everything(playback, session, resolver, resolve_to):
    resolve_to(resolver, "a", "b")
    await session.enqueue("q", 7, CHANNEL)

    await call(playback.stop, playback, interaction_in())

    assert session.queue.current is None
    assert len(session.queue) == 0


async def test_leave_closes_session(playback, session, resolver, resolve_to, voice, closed_guilds):
    resolve_to(resolver, "a")
    await session.enqueue("q", 7, CHANNEL)

    await call(playback.leave, playback, interaction_in())

    assert closed_guilds == [1]
    assert not voice.connected


async def test_volume_sets_session_volume(playback, session, resolver, resolve_to):
    resolve_to(resolver, "a")
    await session.enqueue("q", 7, CHANNEL)

    interaction = interaction_in()
    await call(playback.volume, playback, interaction, 90)

    assert session.volume == 90
    assert "90" in said(interaction)


async def test_nowplaying_sends_embed(playback, session, resolver, resolve_to):
    resolve_to(resolver, "a")
    await session.enqueue("q", 7, CHANNEL)

    interaction = interaction_in()
    await call(playback.nowplaying, playback, interaction)

    assert interaction.response.send_message.await_args.kwargs["embed"].description


async def test_control_commands_reject_user_in_other_channel(
    playback, session, resolver, resolve_to
):
    resolve_to(resolver, "a")
    await session.enqueue("q", 7, CHANNEL)

    with pytest.raises(BotError):
        await call(playback.skip, playback, interaction_in(channel_id=99))


async def test_queue_command_shows_page(queue_cog, session, resolver, resolve_to):
    resolve_to(resolver, "a", "b")
    await session.enqueue("q", 7, CHANNEL)

    interaction = interaction_in()
    await call(queue_cog.queue, queue_cog, interaction, 1)

    assert "Página 1/1" in interaction.response.send_message.await_args.kwargs["embed"].footer.text


async def test_remove_clear_and_shuffle(queue_cog, session, resolver, resolve_to):
    resolve_to(resolver, "playing", "b", "c", "d")
    await session.enqueue("q", 7, CHANNEL)

    await call(queue_cog.remove, queue_cog, interaction_in(), 1)
    assert [t.title for t in session.queue.pending] == ["c", "d"]

    await call(queue_cog.shuffle, queue_cog, interaction_in())

    await call(queue_cog.clear, queue_cog, interaction_in())
    assert len(session.queue) == 0


async def test_shuffle_needs_at_least_two_songs(queue_cog, session, resolver, resolve_to):
    resolve_to(resolver, "playing", "b")
    await session.enqueue("q", 7, CHANNEL)

    with pytest.raises(BotError):
        await call(queue_cog.shuffle, queue_cog, interaction_in())


async def test_loop_command_changes_mode(queue_cog, session, resolver, resolve_to):
    resolve_to(resolver, "a")
    await session.enqueue("q", 7, CHANNEL)

    await call(queue_cog.loop, queue_cog, interaction_in(), SimpleNamespace(value="queue"))

    assert session.loop_mode is LoopMode.QUEUE


def voice_event(registry, humans, bot_id=99, member_id=5, after_channel="voice"):
    client = SimpleNamespace(
        channel=SimpleNamespace(
            members=[SimpleNamespace(bot=False)] * humans + [SimpleNamespace(bot=True)]
        )
    )
    guild = SimpleNamespace(id=1, me=SimpleNamespace(id=bot_id), voice_client=client)
    member = SimpleNamespace(id=member_id, guild=guild)
    return (
        VoiceEventsCog(registry),
        member,
        SimpleNamespace(channel=None),
        SimpleNamespace(channel=after_channel),
    )


async def test_leaving_last_human_marks_channel_empty(registry, observer):
    cog, member, before, after = voice_event(registry, humans=0)

    await cog.on_voice_state_update(member, before, after)

    assert observer.events == ["channel_empty"]


async def test_bots_do_not_count_as_people(registry, observer):
    cog, member, before, after = voice_event(registry, humans=0)

    await cog.on_voice_state_update(member, before, after)

    assert "channel_occupied" not in observer.events


async def test_someone_present_marks_channel_occupied(registry, observer):
    cog, member, before, after = voice_event(registry, humans=2)

    await cog.on_voice_state_update(member, before, after)

    assert observer.events == ["channel_occupied"]


async def test_bot_being_disconnected_closes_session(registry, closed_guilds, voice):
    cog, member, before, after = voice_event(registry, humans=1, member_id=99, after_channel=None)

    await cog.on_voice_state_update(member, before, after)

    assert closed_guilds == [1]


async def test_voice_events_ignored_without_session():
    cog, member, before, after = voice_event(SessionRegistry(lambda g, c: None), humans=0)

    await cog.on_voice_state_update(member, before, after)


async def test_bot_registers_expected_commands():
    bot = MusicBot(SessionRegistry(lambda g, c: None))
    await bot.register_cogs()

    names = {command.name for command in bot.tree.get_commands()}

    assert names == {
        "play", "skip", "pause", "resume", "stop", "leave", "volume",
        "nowplaying", "queue", "remove", "clear", "shuffle", "loop",
    }  # fmt: skip
    await bot.close()


async def test_bot_syncs_to_guild_when_configured():
    bot = MusicBot(SessionRegistry(lambda g, c: None), guild_id=123)
    bot.tree.sync = AsyncMock()

    await bot.sync_commands()

    assert bot.tree.sync.await_args.kwargs["guild"].id == 123


async def test_bot_syncs_globally_without_guild():
    bot = MusicBot(SessionRegistry(lambda g, c: None))
    bot.tree.sync = AsyncMock()

    await bot.sync_commands()

    bot.tree.sync.assert_awaited_once_with()


async def test_bot_close_closes_every_session(session, closed_guilds, voice):
    registry = SessionRegistry(lambda guild_id, on_closed: session)
    registry.get_or_create(1)
    bot = MusicBot(registry)

    await bot.close()

    assert closed_guilds == [1]


def test_ensure_ffmpeg_fails_with_installation_hint(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: None)

    with pytest.raises(SystemExit) as caught:
        ensure_ffmpeg()

    assert str(caught.value) == FFMPEG_HINT


def test_ensure_ffmpeg_passes_when_installed(monkeypatch):
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/ffmpeg")

    ensure_ffmpeg()


def test_load_settings_reports_missing_variables(monkeypatch):
    monkeypatch.delenv("DISCORD_TOKEN", raising=False)
    monkeypatch.chdir("/")

    with pytest.raises(SystemExit) as caught:
        load_settings()

    assert "DISCORD_TOKEN" in str(caught.value)


async def test_composition_root_wires_inactivity_policy(monkeypatch):
    monkeypatch.setenv("DISCORD_TOKEN", "t")
    monkeypatch.chdir("/")
    bot = build_bot(load_settings(), MagicMock())

    created = bot.registry.get_or_create(5)

    assert created.guild_id == 5
    assert type(created._observer).__name__ == "InactivityPolicy"
    assert bot.registry.get(5) is created
    await bot.close()


async def test_rejected_token_exits_with_actionable_message(monkeypatch):
    import discord

    from bot import main

    monkeypatch.setenv("DISCORD_TOKEN", "malo")
    monkeypatch.chdir("/")
    monkeypatch.setattr("shutil.which", lambda name: "/usr/bin/ffmpeg")

    async def reject(self, token):
        raise discord.LoginFailure("Improper token has been passed.")

    monkeypatch.setattr(main.MusicBot, "start", reject)

    with pytest.raises(SystemExit) as caught:
        await main.run()

    assert str(caught.value) == main.TOKEN_HINT
    assert "malo" not in str(caught.value)
