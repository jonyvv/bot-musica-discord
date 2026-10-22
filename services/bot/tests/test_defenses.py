import asyncio
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock

import discord
import pytest
from discord import app_commands

from bot.application.registry import SessionRegistry
from bot.application.session import GuildSession, SessionSettings
from bot.domain.errors import InvalidRequestError, VoiceError
from bot.domain.models import CollectionKind, Resolution, StreamInfo
from bot.domain.text import clean_text, escape_markup, safe_url
from bot.infrastructure.resolver_client import _to_track
from bot.infrastructure.voice import DiscordVoiceGateway
from bot.presentation.bot import MusicBot
from bot.presentation.errors import describe
from bot.presentation.limits import NOT_ALLOWED, InteractionGate
from bot.presentation.permissions import risky_permissions

CHANNEL = 10


class FakeClock:
    def __init__(self):
        self.now = 1000.0

    def __call__(self):
        return self.now


def interaction(user_id=1, guild_id=500):
    return SimpleNamespace(guild_id=guild_id, user=SimpleNamespace(id=user_id))


@pytest.fixture
def clock():
    return FakeClock()


async def test_gate_allows_everything_when_no_guild_list_is_configured(clock):
    gate = InteractionGate(clock=clock)

    assert await gate.check(interaction(guild_id=123456)) is True


async def test_gate_rejects_servers_outside_the_allow_list(clock):
    gate = InteractionGate(frozenset({500}), clock=clock)

    with pytest.raises(app_commands.CheckFailure) as caught:
        await gate.check(interaction(guild_id=999))

    assert str(caught.value) == NOT_ALLOWED
    assert await gate.check(interaction(guild_id=500)) is True


async def test_a_user_spamming_commands_is_cut_off(clock):
    gate = InteractionGate(per_user=(8, 10.0), clock=clock)

    results = []
    for _ in range(40):
        try:
            await gate.check(interaction(user_id=7))
            results.append("ok")
        except app_commands.CommandOnCooldown:
            results.append("limited")

    assert results.count("ok") == 8
    assert results.count("limited") == 32


async def test_the_limit_resets_after_the_window(clock):
    gate = InteractionGate(per_user=(2, 10.0), clock=clock)
    await gate.check(interaction())
    await gate.check(interaction())
    with pytest.raises(app_commands.CommandOnCooldown):
        await gate.check(interaction())

    clock.now += 11

    assert await gate.check(interaction()) is True


async def test_other_users_are_not_affected_by_one_spammer(clock):
    gate = InteractionGate(per_user=(1, 10.0), per_guild=(1000, 10.0), clock=clock)
    await gate.check(interaction(user_id=1))
    with pytest.raises(app_commands.CommandOnCooldown):
        await gate.check(interaction(user_id=1))

    assert await gate.check(interaction(user_id=2)) is True


async def test_many_accounts_together_hit_the_per_server_limit(clock):
    gate = InteractionGate(per_user=(100, 10.0), per_guild=(30, 10.0), clock=clock)

    outcomes = []
    for user in range(200):
        try:
            await gate.check(interaction(user_id=user))
            outcomes.append(True)
        except app_commands.CommandOnCooldown:
            outcomes.append(False)

    assert sum(outcomes) == 30


async def test_gate_memory_stays_bounded_under_a_flood_of_distinct_accounts(clock):
    gate = InteractionGate(
        max_tracked=1000, per_user=(5, 10.0), per_guild=(10**9, 10.0), clock=clock
    )

    for user in range(30_000):
        await gate.check(interaction(user_id=user))

    assert len(gate._users) <= 1000


async def test_direct_messages_are_limited_per_user_too(clock):
    gate = InteractionGate(per_user=(2, 10.0), clock=clock)
    await gate.check(interaction(guild_id=None))
    await gate.check(interaction(guild_id=None))

    with pytest.raises(app_commands.CommandOnCooldown):
        await gate.check(interaction(guild_id=None))


def test_users_get_a_clear_message_for_each_rejection():
    assert "habilitado" in describe(app_commands.CheckFailure(NOT_ALLOWED))
    cooldown = app_commands.CommandOnCooldown(app_commands.Cooldown(1, 5.0), 4.0)
    assert "4" in describe(cooldown)


def test_gate_is_installed_on_the_command_tree():
    bot = MusicBot(SessionRegistry(lambda g, c: None), gate=InteractionGate(frozenset({1})))

    assert bot.tree.interaction_check == bot.gate.check


def test_bot_never_pings_anyone_by_default():
    bot = MusicBot(SessionRegistry(lambda g, c: None))

    mentions = bot.allowed_mentions
    assert mentions.everyone is False
    assert mentions.users is False
    assert mentions.roles is False


async def test_bot_leaves_servers_that_are_not_allowed():
    bot = MusicBot(SessionRegistry(lambda g, c: None), gate=InteractionGate(frozenset({500})))
    stranger = SimpleNamespace(id=999, leave=AsyncMock())

    await bot.leave_if_not_allowed(stranger)

    stranger.leave.assert_awaited_once()


async def test_bot_stays_in_allowed_servers_and_warns_about_excess_permissions(caplog):
    bot = MusicBot(SessionRegistry(lambda g, c: None), gate=InteractionGate(frozenset({500})))
    perms = discord.Permissions(administrator=True, ban_members=True, connect=True)
    home = SimpleNamespace(id=500, leave=AsyncMock(), me=SimpleNamespace(guild_permissions=perms))

    with caplog.at_level(logging.WARNING):
        await bot.leave_if_not_allowed(home)

    home.leave.assert_not_awaited()
    assert "administrator" in caplog.text
    assert "ban_members" in caplog.text


def test_risky_permissions_ignores_what_a_music_bot_legitimately_needs():
    needed = discord.Permissions(connect=True, speak=True, send_messages=True, embed_links=True)

    assert risky_permissions(needed) == []
    assert "kick_members" in risky_permissions(discord.Permissions(kick_members=True))


@pytest.mark.parametrize(
    ("hostile", "forbidden"),
    [
        ("Song‮ gnp.exe", "‮"),
        ("Song​‍ hidden", "​"),
        ("line1\nline2\rline3", "\n"),
        ("null\x00byte", "\x00"),
        ("`code` ``break``", "`"),
    ],
)
def test_clean_text_removes_invisible_and_control_characters(hostile, forbidden):
    assert forbidden not in clean_text(hostile)


def test_clean_text_bounds_length_and_handles_empty_values():
    assert len(clean_text("x" * 10_000)) == 150
    assert clean_text("​‮ \n") is None
    assert clean_text(None) is None


@pytest.mark.parametrize(
    "hostile",
    [
        "[Haz clic](https://evil.example)",
        "@everyone @here <@123456789> <@&99> <#5>",
        "**negrita** __sub__ ~~tachado~~ ||spoiler|| > cita",
        "# titulo grande",
    ],
)
def test_escape_markup_neutralises_discord_formatting(hostile):
    escaped = escape_markup(hostile)

    for char in "*_~|>#[]()<@":
        for index, found in enumerate(escaped):
            if found == char:
                assert escaped[index - 1] == "\\", f"{char!r} sin escapar en {escaped!r}"


@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(1)",
        "http://insecure.example/a",
        "https://x.example/a)[click](https://evil.example",
        "https://x.example/a b",
        "https://x.example/<script>",
        "https://x.example/‮",
        "https://x.example/" + "a" * 3000,
        "",
        None,
    ],
)
def test_unsafe_urls_are_dropped(url):
    assert safe_url(url) is None


def test_ordinary_https_urls_are_kept():
    url = "https://i.ytimg.com/vi/abcdefghijk/maxresdefault.jpg"

    assert safe_url(url) == url


def test_resolver_response_is_sanitised_at_the_boundary():
    track = _to_track(
        {
            "title": "[Gratis](https://evil.example) ‮ @everyone `x`",
            "artist": "Art​ist\n",
            "source": "youtube",
            "duration_seconds": -5,
            "webpage_url": "https://x.example/a)(b",
            "thumbnail_url": "javascript:alert(1)",
            "search_query": "a\nb",
            "is_live": "yes",
        }
    )

    assert "‮" not in track.title
    assert "`" not in track.title
    assert track.artist == "Artist"
    assert track.duration_seconds is None
    assert track.webpage_url is None
    assert track.thumbnail_url is None
    assert track.search_query == "a b"
    assert track.is_live is True


class SlowResolver:
    def __init__(self, make_track):
        self.make_track = make_track
        self.release = asyncio.Event()
        self.started = 0

    async def resolve(self, query):
        self.started += 1
        await self.release.wait()
        return Resolution(CollectionKind.TRACK, None, (self.make_track("a"),))

    async def stream(self, track):
        return StreamInfo(url="https://a", headers={}, expires_at=None, webpage_url="w")


def session_with(resolver, voice, notifier, **limits):
    return GuildSession(
        guild_id=1,
        resolver=resolver,
        voice=voice,
        notifier=notifier,
        settings=SessionSettings(**limits),
    )


async def test_a_flood_of_simultaneous_requests_is_capped_per_server(make_track, voice, notifier):
    resolver = SlowResolver(make_track)
    session = session_with(resolver, voice, notifier, max_inflight=3)
    pending = [asyncio.create_task(session.enqueue("q", 1, CHANNEL)) for _ in range(3)]
    await asyncio.sleep(0)

    with pytest.raises(InvalidRequestError):
        await session.enqueue("q", 1, CHANNEL)
    resolver.release.set()
    await asyncio.gather(*pending)

    assert resolver.started == 3


async def test_slots_are_freed_when_a_request_fails(make_track, voice, notifier):
    class Failing:
        async def resolve(self, query):
            raise InvalidRequestError("no")

    session = session_with(Failing(), voice, notifier, max_inflight=1)

    for _ in range(5):
        with pytest.raises(InvalidRequestError, match="no"):
            await session.enqueue("q", 1, CHANNEL)


async def test_one_user_cannot_fill_the_queue_alone(resolver, voice, notifier, resolve_to):
    session = session_with(resolver, voice, notifier, max_tracks_per_user=4, max_queue_size=100)
    resolve_to(resolver, *[f"t{i}" for i in range(10)])

    first = await session.enqueue("q", 7, CHANNEL)

    assert first.added == 4
    with pytest.raises(InvalidRequestError, match="máximo"):
        await session.enqueue("q", 7, CHANNEL)


async def test_the_per_user_quota_does_not_block_other_users(resolver, voice, notifier, resolve_to):
    session = session_with(resolver, voice, notifier, max_tracks_per_user=2, max_queue_size=100)
    resolve_to(resolver, "a", "b", "c")
    await session.enqueue("q", 7, CHANNEL)

    other = await session.enqueue("q", 8, CHANNEL)

    assert other.added == 2


async def test_zero_quota_means_unlimited_per_user(resolver, voice, notifier, resolve_to):
    session = session_with(resolver, voice, notifier, max_tracks_per_user=0, max_queue_size=100)
    resolve_to(resolver, *[f"t{i}" for i in range(30)])

    assert (await session.enqueue("q", 7, CHANNEL)).added == 30


async def test_voice_rejects_urls_that_ffmpeg_could_use_to_read_local_files(monkeypatch):
    client = SimpleNamespace(is_connected=lambda: True, play=lambda *a, **k: None)
    bot = SimpleNamespace(get_guild=lambda guild_id: SimpleNamespace(voice_client=client))
    gateway = DiscordVoiceGateway(bot, 1)
    called = []
    monkeypatch.setattr(discord, "FFmpegPCMAudio", lambda *a, **k: called.append(a))

    for evil in ("file:///etc/passwd", "concat:file:///etc/passwd|https://x", "-i /etc/passwd"):
        stream = StreamInfo(url=evil, headers={}, expires_at=None, webpage_url="w")
        with pytest.raises(VoiceError):
            await gateway.play(stream, 50, on_finished=lambda error: asyncio.sleep(0))

    assert called == []
