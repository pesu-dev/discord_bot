from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from bson import ObjectId

from src.cogs.anon import SlashAnon
from src.cogs.anon.commands import AnonCommands
from src.data.mongo import AnonMute
from tests.helpers import get_callback

if TYPE_CHECKING:
    from tests.conftest import InteractionFactory, MemberFactory


def _gate_anon_send_ok(mock_bot: MagicMock) -> None:
    mock_bot.stores.links.exists = AsyncMock(return_value=True)
    mock_bot.stores.anon_bans.has_active = AsyncMock(return_value=False)
    mock_bot.stores.anon_mutes.find_active = AsyncMock(return_value=None)


async def test_anon_send_locked_channel(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonCommands()
    cmd.client = mock_bot
    _gate_anon_send_ok(mock_bot)
    mock_bot.config.lobby_channel.permissions_for = MagicMock(return_value=MagicMock(send_messages=False))
    interaction = interaction_factory(user=member_factory())
    await get_callback(cmd.anon_send)(cmd, interaction, "hello")
    assert "locked" in interaction.followup.send.await_args.kwargs["content"].lower()


async def test_anon_send_reply_link(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonCommands()
    cmd.client = mock_bot
    _gate_anon_send_ok(mock_bot)
    mock_bot.config.lobby_channel.permissions_for = MagicMock(return_value=MagicMock(send_messages=True))
    reply_msg = MagicMock()
    sent = MagicMock()
    sent.id = 777
    reply_msg.reply = AsyncMock(return_value=sent)
    mock_bot.config.lobby_channel.fetch_message = AsyncMock(return_value=reply_msg)
    interaction = interaction_factory(user=member_factory(user_id=1001))
    await get_callback(cmd.anon_send)(cmd, interaction, "hi", link="https://discord.com/channels/1/2/9")
    reply_msg.reply.assert_awaited()
    assert mock_bot.anon_cache["1001"][0]["message_id"] == "777"


async def test_anon_send_bad_reply_link(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonCommands()
    cmd.client = mock_bot
    _gate_anon_send_ok(mock_bot)
    mock_bot.config.lobby_channel.permissions_for = MagicMock(return_value=MagicMock(send_messages=True))
    mock_bot.config.lobby_channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "x"))
    sent = MagicMock(id=1)
    mock_bot.config.lobby_channel.send = AsyncMock(return_value=sent)
    interaction = interaction_factory(user=member_factory(user_id=1001))
    await get_callback(cmd.anon_send)(cmd, interaction, "hi", link="https://discord.com/channels/1/2/9")
    mock_bot.config.lobby_channel.send.assert_awaited()


async def test_anon_send_reuses_cache_key(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonCommands()
    cmd.client = mock_bot
    _gate_anon_send_ok(mock_bot)
    mock_bot.config.lobby_channel.permissions_for = MagicMock(return_value=MagicMock(send_messages=True))
    sent = MagicMock(id=99)
    mock_bot.config.lobby_channel.send = AsyncMock(return_value=sent)
    mock_bot.anon_cache = {"1001": []}
    interaction = interaction_factory(user=member_factory(user_id=1001))
    await get_callback(cmd.anon_send)(cmd, interaction, "hi")
    assert len(mock_bot.anon_cache["1001"]) == 1
    assert mock_bot.anon_cache["1001"][0]["message_id"] == "99"


async def test_anon_send_muted_shows_unmute_time(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonCommands()
    cmd.client = mock_bot
    mock_bot.stores.links.exists = AsyncMock(return_value=True)
    mock_bot.stores.anon_bans.has_active = AsyncMock(return_value=False)
    unmute_at = datetime.now(UTC) + timedelta(hours=2)
    mock_bot.stores.anon_mutes.find_active = AsyncMock(
        return_value=AnonMute(
            discord_user_id="1001",
            moderator_discord_user_id="1",
            muted_at=datetime.now(UTC),
            original_unmute_time=unmute_at,
            reason="spam",
        )
    )
    interaction = interaction_factory(user=member_factory(user_id=1001))
    await get_callback(cmd.anon_send)(cmd, interaction, "hi")
    content = interaction.followup.send.await_args.kwargs["content"]
    assert "muted from using anon messaging until" in content
    assert discord.utils.format_dt(unmute_at, "R") in content


def _expired_anon_mute(*, mute_id: ObjectId | None) -> AnonMute:
    now = datetime.now(UTC)
    return AnonMute(
        id=mute_id,
        discord_user_id="55",
        moderator_discord_user_id="1",
        muted_at=now - timedelta(hours=1),
        original_unmute_time=now - timedelta(seconds=1),
        reason="expired",
    )


async def test_anon_mute_loop_expires(mock_bot: MagicMock) -> None:
    with patch.object(
        SlashAnon,
        "__init__",
        lambda self, client: setattr(self, "client", client) or setattr(self, "tasks", []),
    ):
        cog = SlashAnon(mock_bot)

    mute = _expired_anon_mute(mute_id=ObjectId())
    mock_bot.stores.anon_mutes.find_expired = AsyncMock(return_value=[mute])
    mock_bot.stores.anon_mutes.mark_unmuted = AsyncMock()
    user = MagicMock()
    mock_bot.fetch_user = AsyncMock(return_value=user)
    with patch("src.utils.general.send_dm_safely", AsyncMock(return_value=True)) as dm:
        await SlashAnon.check_anon_mutes_loop(cog)
    kwargs = mock_bot.stores.anon_mutes.mark_unmuted.await_args.kwargs
    mock_bot.stores.anon_mutes.mark_unmuted.assert_awaited_once_with(mute.id, unmuted_at=kwargs["unmuted_at"])
    dm.assert_awaited()


async def test_anon_mute_loop_skips_missing_id(mock_bot: MagicMock) -> None:
    with patch.object(
        SlashAnon,
        "__init__",
        lambda self, client: setattr(self, "client", client) or setattr(self, "tasks", []),
    ):
        cog = SlashAnon(mock_bot)

    mute = _expired_anon_mute(mute_id=None)
    mock_bot.stores.anon_mutes.find_expired = AsyncMock(return_value=[mute])
    mock_bot.stores.anon_mutes.mark_unmuted = AsyncMock()
    await SlashAnon.check_anon_mutes_loop(cog)
    mock_bot.stores.anon_mutes.mark_unmuted.assert_not_called()


async def test_anon_before_loops(mock_bot: MagicMock) -> None:
    with patch.object(
        SlashAnon,
        "__init__",
        lambda self, client: setattr(self, "client", client) or setattr(self, "tasks", []),
    ):
        cog = SlashAnon(mock_bot)
    mock_bot.wait_until_ready = AsyncMock()
    await SlashAnon.before_check_anon_mutes_loop(cog)
    await SlashAnon.before_clear_anon_cache_loop(cog)
    assert mock_bot.wait_until_ready.await_count == 2


async def test_slash_anon_lifecycle(mock_bot: MagicMock) -> None:
    mock_bot.wait_until_ready = AsyncMock()
    with (
        patch("discord.ext.tasks.Loop.start"),
        patch("discord.ext.tasks.Loop.is_running", return_value=False),
        patch("discord.ext.tasks.Loop.cancel"),
    ):
        cog = SlashAnon(mock_bot)
        assert len(cog.tasks) == 2
        await cog.on_ready()
        await cog.cog_unload()


async def test_slash_anon_skips_start_when_running(mock_bot: MagicMock) -> None:
    from discord.ext import tasks

    mock_bot.wait_until_ready = AsyncMock()

    def is_running_skip_start(self: object) -> bool:
        # Loop construction calls is_running before _last_iteration exists.
        if not hasattr(self, "_last_iteration"):
            return False
        return True

    with (
        patch.object(tasks.Loop, "is_running", is_running_skip_start),
        patch.object(tasks.Loop, "start") as start,
        patch.object(tasks.Loop, "cancel"),
    ):
        cog = SlashAnon(mock_bot)
        await cog.on_ready()
    start.assert_not_called()


async def test_anon_mute_loop_fetch_user_none(mock_bot: MagicMock) -> None:
    with patch.object(
        SlashAnon,
        "__init__",
        lambda self, client: setattr(self, "client", client) or setattr(self, "tasks", []),
    ):
        cog = SlashAnon(mock_bot)

    mute = _expired_anon_mute(mute_id=ObjectId())
    mock_bot.stores.anon_mutes.find_expired = AsyncMock(return_value=[mute])
    mock_bot.stores.anon_mutes.mark_unmuted = AsyncMock()
    mock_bot.fetch_user = AsyncMock(return_value=None)
    await SlashAnon.check_anon_mutes_loop(cog)
    kwargs = mock_bot.stores.anon_mutes.mark_unmuted.await_args.kwargs
    mock_bot.stores.anon_mutes.mark_unmuted.assert_awaited_once_with(mute.id, unmuted_at=kwargs["unmuted_at"])


async def test_clear_anon_cache_empty(mock_bot: MagicMock) -> None:
    with patch.object(
        SlashAnon,
        "__init__",
        lambda self, client: setattr(self, "client", client) or setattr(self, "tasks", []),
    ):
        cog = SlashAnon(mock_bot)
    mock_bot.anon_cache = {}
    await SlashAnon.clear_anon_cache_loop(cog)
    assert mock_bot.anon_cache == {}
