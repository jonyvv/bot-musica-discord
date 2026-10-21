from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import discord
import pytest
from discord import app_commands

from bot.application.registry import SessionRegistry
from bot.application.session import PlaybackState
from bot.domain.errors import BotError, InvalidRequestError, NotPlayingError
from bot.domain.models import CollectionKind, LoopMode, Resolution
from bot.presentation import embeds, guards
from bot.presentation.errors import describe, handle_command_error
from bot.presentation.formatting import format_duration, progress_bar, safe, truncate

CHANNEL = 10


def fake_channel(
    channel_id=CHANNEL, members=(), user_limit=0, connect=True, speak=True, move=False
):
    permissions = SimpleNamespace(connect=connect, speak=speak, move_members=move)
    return SimpleNamespace(
        id=channel_id,
        mention=f"<#{channel_id}>",
        members=list(members),
        user_limit=user_limit,
        permissions_for=lambda member: permissions,
    )


def fake_interaction(channel=None, guild_id=1, user_id=7):
    voice = SimpleNamespace(channel=channel) if channel is not None else None
    guild = SimpleNamespace(id=guild_id, me=object())
    response = SimpleNamespace(
        defer=AsyncMock(), send_message=AsyncMock(), is_done=MagicMock(return_value=False)
    )
    return SimpleNamespace(
        guild=guild,
        user=SimpleNamespace(id=user_id, voice=voice),
        channel_id=555,
        response=response,
        followup=SimpleNamespace(send=AsyncMock()),
    )


@pytest.fixture
def registry(session):
    created = SessionRegistry(lambda guild_id, on_closed: session)
    created.get_or_create(1)
    return created


async def start(session, resolver, resolve_to, *titles):
    resolve_to(resolver, *titles)
    return await session.enqueue("q", 7, CHANNEL)


def test_format_duration():
    assert format_duration(None) == "--:--"
    assert format_duration(65) == "1:05"
    assert format_duration(3725) == "1:02:05"
    assert format_duration(0) == "0:00"


def test_progress_bar_marks_position_and_handles_unknown_total():
    assert progress_bar(10, None) == ""
    assert progress_bar(0, 100).startswith("🔘")
    assert progress_bar(500, 100).endswith("🔘")
    assert len(progress_bar(50, 100)) == 18


def test_truncate_and_safe_neutralise_markdown():
    assert truncate("abcdef", 4) == "abc…"
    assert truncate("abc", 4) == "abc"
    assert "\\*" in safe("**bold**")


def test_guard_requires_guild():
    interaction = fake_interaction(fake_channel())
    interaction.guild = None

    with pytest.raises(BotError):
        guards.guild_of(interaction)


def test_guard_requires_user_in_voice_channel():
    with pytest.raises(BotError):
        guards.voice_channel_of(fake_interaction(channel=None))


def test_guard_rejects_missing_permissions():
    with pytest.raises(BotError):
        guards.require_permissions(fake_channel(speak=False), object())


def test_guard_rejects_full_channel_unless_bot_can_move_members():
    full = fake_channel(user_limit=1, members=[object()])
    with pytest.raises(BotError):
        guards.require_permissions(full, object())

    guards.require_permissions(fake_channel(user_limit=1, members=[object()], move=True), object())


async def test_controlled_session_requires_active_session(registry):
    empty = SessionRegistry(lambda guild_id, on_closed: None)

    with pytest.raises(BotError):
        guards.controlled_session(fake_interaction(fake_channel()), empty)


async def test_controlled_session_requires_same_voice_channel(
    registry, session, resolver, resolve_to
):
    await start(session, resolver, resolve_to, "a")

    with pytest.raises(BotError):
        guards.controlled_session(fake_interaction(fake_channel(channel_id=99)), registry)

    assert guards.controlled_session(fake_interaction(fake_channel()), registry) is session


async def test_play_target_returns_session_and_channel(registry, session):
    interaction = fake_interaction(fake_channel())

    result_session, channel = guards.play_target(interaction, registry)

    assert result_session is session
    assert channel.id == CHANNEL


def test_describe_user_facing_errors_directly():
    assert describe(app_commands.AppCommandError()) != ""
    wrapped = app_commands.CommandInvokeError(MagicMock(), BotError("hola"))
    assert describe(wrapped) == "hola"


def test_describe_hides_unexpected_errors_from_users(caplog):
    wrapped = app_commands.CommandInvokeError(MagicMock(), RuntimeError("password=secret"))

    message = describe(wrapped)

    assert "secret" not in message
    assert "inesperado" in message


def test_describe_cooldown():
    cooldown = app_commands.Cooldown(1, 2.0)
    error = app_commands.CommandOnCooldown(cooldown, 1.4)

    assert "1" in describe(error)


async def test_handle_error_uses_response_or_followup():
    fresh = fake_interaction(fake_channel())
    await handle_command_error(fresh, app_commands.CommandInvokeError(MagicMock(), BotError("x")))
    fresh.response.send_message.assert_awaited_once()

    deferred = fake_interaction(fake_channel())
    deferred.response.is_done.return_value = True
    await handle_command_error(
        deferred, app_commands.CommandInvokeError(MagicMock(), BotError("x"))
    )
    deferred.followup.send.assert_awaited_once()


async def test_now_playing_embed_shows_track_progress_and_requester(session, resolver, resolve_to):
    await start(session, resolver, resolve_to, "Song")

    embed = embeds.now_playing_embed(session)

    assert "Song" in embed.description
    assert any("<@7>" in field.value for field in embed.fields)
    assert any("0:00 / 3:20" in field.value for field in embed.fields)


async def test_now_playing_embed_reflects_pause(session, resolver, resolve_to):
    await start(session, resolver, resolve_to, "Song")
    session.pause()

    assert "pausa" in embeds.now_playing_embed(session).title.lower()
    assert session.state is PlaybackState.PAUSED


async def test_now_playing_without_track_fails(session):
    with pytest.raises(NotPlayingError):
        embeds.now_playing_embed(session)


async def test_queue_embed_paginates_and_reports_totals(session, resolver, resolve_to):
    await start(session, resolver, resolve_to, "playing")
    await start(session, resolver, resolve_to, *[f"t{i}" for i in range(5)])
    session.queue._max_size = 100
    session.queue.add(session.queue.pending * 2)

    first = embeds.queue_embed(session, 1)
    second = embeds.queue_embed(session, 2)

    assert first.description.count("`") == 20
    assert "Página 1/2" in first.footer.text
    assert "Página 2/2" in second.footer.text
    with pytest.raises(InvalidRequestError):
        embeds.queue_embed(session, 3)


async def test_empty_queue_embed(session, resolver, resolve_to):
    await start(session, resolver, resolve_to, "only")

    assert "vacía" in embeds.queue_embed(session, 1).description


async def test_enqueued_embed_for_single_track(session, resolver, resolve_to):
    result = await start(session, resolver, resolve_to, "Song")
    assert "Reproduciendo ahora" in embeds.enqueued_embed(result).title

    queued = await start(session, resolver, resolve_to, "Other")
    assert "posición 1" in embeds.enqueued_embed(queued).title


async def test_enqueued_embed_for_collection_reports_limits(session, resolver, resolve_to):
    resolve_to(resolver, *[f"t{i}" for i in range(8)])
    resolver.resolution = Resolution(
        CollectionKind.PLAYLIST, "Mix", resolver.resolution.tracks, truncated=True
    )
    result = await session.enqueue("q", 7, CHANNEL)

    embed = embeds.enqueued_embed(result)

    assert "Agregadas 5" in embed.title
    assert "Mix" in embed.description
    assert {field.name for field in embed.fields} == {"Cola llena", "Lista recortada"}


def test_loop_labels_cover_every_mode():
    assert all(embeds.loop_label(mode) for mode in LoopMode)


def test_embeds_are_real_discord_embeds(session):
    assert isinstance(embeds.queue_embed(session, 1), discord.Embed)
