from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import pytest
from discord.ext import commands
from pymongo.errors import DuplicateKeyError, PyMongoError

from src.cogs.mod.commands import ModCommands
from src.cogs.mod.helpers import ModHelpers
from src.data.mongo import Link, ServerBan
from tests.helpers import get_callback

if TYPE_CHECKING:
    from tests.conftest import InteractionFactory, MemberFactory


class _Helpers(ModHelpers):
    pass


async def test_kick_mod_target_blocked(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[mock_bot.config.mod_role])
    interaction = interaction_factory(user=mod)
    await get_callback(cmd.kick)(cmd, interaction, target, "spam")
    assert interaction.followup.send.await_args.kwargs.get("ephemeral") is True
    target.kick.assert_not_awaited()


async def test_kick_junior_mod_target_blocked(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[mock_bot.config.junior_mod_role])
    interaction = interaction_factory(user=mod)
    await get_callback(cmd.kick)(cmd, interaction, target, "spam")
    assert interaction.followup.send.await_args.kwargs.get("ephemeral") is True
    target.kick.assert_not_awaited()


async def test_echo_with_and_without_attachment(mock_bot: MagicMock) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    channel = MagicMock(spec=discord.TextChannel)
    channel.mention = "<#1>"
    channel.send = AsyncMock()
    ctx = MagicMock(spec=commands.Context)
    ctx.send = AsyncMock()
    ctx.author = MagicMock()
    ctx.author.mention = "<@1>"
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    await get_callback(cmd.echo)(cmd, ctx, channel, None, message="hello")
    channel.send.assert_awaited_with(content="hello")

    attachment = MagicMock(spec=discord.Attachment)
    fake_file = MagicMock()
    attachment.to_file = AsyncMock(return_value=fake_file)
    channel.send.reset_mock()
    await get_callback(cmd.echo)(cmd, ctx, channel, attachment, message="with file")
    channel.send.assert_awaited_with(content="with file", file=fake_file)


async def test_mute_invalid_time(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=3, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2)
    interaction = interaction_factory(user=mod)
    interaction.user = mod
    await get_callback(cmd.mute)(cmd, interaction, target, "bad")
    assert "proper amount of time" in interaction.followup.send.await_args.kwargs["content"]


async def test_mute_junior_mod_authorized(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    junior_mod = member_factory(user_id=1, roles=[mock_bot.config.junior_mod_role])
    target = member_factory(user_id=2, roles=[])
    interaction = interaction_factory(user=junior_mod)
    interaction.user = junior_mod
    mock_bot.stores.mutes.insert_one = AsyncMock()
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    await get_callback(cmd.mute)(cmd, interaction, target, "2h", "noise")
    target.add_roles.assert_awaited_with(mock_bot.config.muted_role)
    mock_bot.stores.mutes.insert_one.assert_awaited()


async def test_mute_already_muted(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(roles=[mock_bot.config.mod_role])
    target = member_factory(roles=[mock_bot.config.muted_role])
    interaction = interaction_factory(user=mod)
    interaction.user = mod
    await get_callback(cmd.mute)(cmd, interaction, target, "1h")
    assert "already muted" in interaction.followup.send.await_args.kwargs["content"]


async def test_unmute_not_muted(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(roles=[mock_bot.config.mod_role])
    target = member_factory(roles=[])
    interaction = interaction_factory(user=mod)
    await get_callback(cmd.unmute)(cmd, interaction, target)
    assert "ain't muted" in interaction.followup.send.await_args.kwargs["content"]


async def test_purge_invalid_amount(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    interaction = interaction_factory(user=member_factory(roles=[mock_bot.config.mod_role]))
    await get_callback(cmd.purge)(cmd, interaction, 0)
    assert "between 1 and 100" in interaction.followup.send.await_args.kwargs["content"]


async def test_lock_unlock_channel(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(roles=[mock_bot.config.mod_role])
    interaction = interaction_factory(user=mod)
    guild = MagicMock(spec=discord.Guild)
    everyone = MagicMock(spec=discord.Role)
    guild.default_role = everyone
    interaction.guild = guild

    overwrites = SimpleNamespace(
        send_messages=True,
        send_messages_in_threads=True,
        create_public_threads=True,
        create_private_threads=True,
    )
    channel = MagicMock(spec=discord.TextChannel)
    channel.mention = "<#3>"
    channel.overwrites_for = MagicMock(return_value=overwrites)
    channel.set_permissions = AsyncMock()
    channel.send = AsyncMock()
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    await get_callback(cmd.lock_channel)(cmd, interaction, channel=channel, reason="raid")
    assert overwrites.send_messages is False
    assert overwrites.send_messages_in_threads is False
    assert overwrites.create_public_threads is False
    assert overwrites.create_private_threads is False
    channel.set_permissions.assert_awaited()

    await get_callback(cmd.unlock_channel)(cmd, interaction, channel=channel)
    assert overwrites.send_messages is None
    assert overwrites.send_messages_in_threads is None
    assert overwrites.create_public_threads is None
    assert overwrites.create_private_threads is None


async def test_lock_unlock_requires_text_channel(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    interaction = interaction_factory(user=member_factory(roles=[mock_bot.config.mod_role]))
    interaction.channel = MagicMock()
    await get_callback(cmd.lock_channel)(cmd, interaction, channel=None)
    assert "text channel" in interaction.followup.send.await_args.kwargs["content"]
    await get_callback(cmd.unlock_channel)(cmd, interaction, channel=None)
    assert "text channel" in interaction.followup.send.await_args.kwargs["content"]


async def test_lock_unlock_uses_interaction_channel(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(roles=[mock_bot.config.mod_role])
    interaction = interaction_factory(user=mod)
    guild = MagicMock(spec=discord.Guild)
    everyone = MagicMock(spec=discord.Role)
    guild.default_role = everyone
    interaction.guild = guild

    overwrites = SimpleNamespace(
        send_messages=True,
        send_messages_in_threads=True,
        create_public_threads=True,
        create_private_threads=True,
    )
    channel = MagicMock(spec=discord.TextChannel)
    channel.mention = "<#9>"
    channel.overwrites_for = MagicMock(return_value=overwrites)
    channel.set_permissions = AsyncMock()
    channel.send = AsyncMock()
    interaction.channel = channel
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    await get_callback(cmd.lock_channel)(cmd, interaction, channel=None, reason="raid")
    assert overwrites.send_messages is False
    channel.set_permissions.assert_awaited()

    await get_callback(cmd.unlock_channel)(cmd, interaction, channel=None)
    assert overwrites.send_messages is None


async def test_timeout_edge_cases(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=9)
    interaction = interaction_factory(user=mod)

    await get_callback(cmd.timeout_member)(cmd, interaction, target, "bad")
    assert "proper amount of time" in interaction.followup.send.await_args.kwargs["content"]

    await get_callback(cmd.timeout_member)(cmd, interaction, target, "30d")
    assert "28 days" in interaction.followup.send.await_args.kwargs["content"]

    target.is_timed_out = MagicMock(return_value=True)
    await get_callback(cmd.timeout_member)(cmd, interaction, target, "10m")
    assert "already timed-out" in interaction.followup.send.await_args.kwargs["content"]


async def test_detimeout(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(roles=[mock_bot.config.mod_role])
    target = member_factory()
    interaction = interaction_factory(user=mod)
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    target.is_timed_out = MagicMock(return_value=False)
    await get_callback(cmd.detimeout_member)(cmd, interaction, target)
    assert "ain't on time-out" in interaction.followup.send.await_args.kwargs["content"]

    target.is_timed_out = MagicMock(return_value=True)
    await get_callback(cmd.detimeout_member)(cmd, interaction, target)
    assert target.timeout.await_args.args[0] is None
    assert "Timeout removed" in target.timeout.await_args.kwargs["reason"]


async def test_handle_anon_message_link(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    member = member_factory(user_id=42)
    guild = MagicMock(spec=discord.Guild)
    guild.get_member = MagicMock(return_value=member)
    channel = MagicMock()
    msg = MagicMock()
    msg.id = 999
    channel.fetch_message = AsyncMock(return_value=msg)
    interaction = interaction_factory(guild=guild, channel=channel)
    interaction.guild = guild
    interaction.channel = channel
    mock_bot.anon_cache = {"42": [{"message_id": "999", "timestamp": MagicMock()}]}

    found = await helpers._handle_anon_message_link(interaction, "https://discord.com/channels/1/2/999")
    assert found is member

    channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "x"))
    assert await helpers._handle_anon_message_link(interaction, "x/1") is None

    channel.fetch_message = AsyncMock(return_value=msg)
    mock_bot.anon_cache = {}
    assert await helpers._handle_anon_message_link(interaction, "x/999") is None


async def test_apply_anon_ban_dm_closed(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    mock_bot.stores.anon_bans.has_active = AsyncMock(return_value=False)
    mock_bot.stores.anon_bans.insert_one = AsyncMock()
    interaction = interaction_factory()
    with patch("src.utils.general.send_dm_safely", AsyncMock(return_value=False)):
        await helpers._apply_anon_ban(interaction, member_factory(), reason="x", message_link="https://x")
    assert any("DMs were closed" in (c.kwargs.get("content") or "") for c in interaction.followup.send.await_args_list)


async def test_kick_dm_forbidden(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    target.send = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "closed"))
    interaction = interaction_factory(user=mod)
    interaction.guild = MagicMock()
    interaction.guild.name = "PESU"
    mock_bot.config.mod_logs_channel.send = AsyncMock()
    await get_callback(cmd.kick)(cmd, interaction, target, "spam")
    target.kick.assert_awaited()


async def test_mute_protected_target(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[mock_bot.config.admin_role])
    interaction = interaction_factory(user=mod)
    interaction.user = mod
    await get_callback(cmd.mute)(cmd, interaction, target, "1h")
    assert interaction.followup.send.await_args.kwargs.get("ephemeral") is True


async def test_mute_junior_mod_target_blocked(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[mock_bot.config.junior_mod_role])
    interaction = interaction_factory(user=mod)
    interaction.user = mod
    await get_callback(cmd.mute)(cmd, interaction, target, "1h")
    assert interaction.followup.send.await_args.kwargs.get("ephemeral") is True


async def test_timeout_protected_target(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(roles=[mock_bot.config.mod_role])
    target = member_factory(roles=[mock_bot.config.mod_role])
    target.is_timed_out = MagicMock(return_value=False)
    interaction = interaction_factory(user=mod)
    await get_callback(cmd.timeout_member)(cmd, interaction, target, "10m")
    assert interaction.followup.send.await_args.kwargs.get("ephemeral") is True


async def test_timeout_junior_mod_target_blocked(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(roles=[mock_bot.config.mod_role])
    target = member_factory(roles=[mock_bot.config.junior_mod_role])
    target.is_timed_out = MagicMock(return_value=False)
    interaction = interaction_factory(user=mod)
    await get_callback(cmd.timeout_member)(cmd, interaction, target, "10m")
    assert interaction.followup.send.await_args.kwargs.get("ephemeral") is True


def _ban_guild(target: MagicMock, *, owner_id: int = 999) -> MagicMock:
    guild = MagicMock(spec=discord.Guild)
    guild.name = "PESU"
    guild.owner_id = owner_id
    guild.get_member = MagicMock(return_value=target)
    guild.ban = AsyncMock()
    return guild


def _unban_guild(*, banned: bool = True) -> MagicMock:
    guild = MagicMock(spec=discord.Guild)
    guild.name = "PESU"
    guild.owner_id = 999
    if banned:
        guild.fetch_ban = AsyncMock(return_value=MagicMock())
    else:
        guild.fetch_ban = AsyncMock(side_effect=discord.NotFound(MagicMock(), "no ban"))
    guild.unban = AsyncMock()
    return guild


async def test_ban_success(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _ban_guild(target)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(
        return_value=Link(discord_user_id="2", prn="PES1UG21CS001"),
    )
    mock_bot.stores.server_bans.insert_one = AsyncMock()
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    with patch("src.cogs.mod.commands.ug.send_dm_safely", AsyncMock(return_value=True)) as send_dm_safely:
        await get_callback(cmd.ban)(cmd, interaction, target, "spam", 2)

    send_dm_safely.assert_awaited_once_with(target, content="You have been banned from **PESU**\nReason: spam")
    guild.ban.assert_awaited_once_with(
        target,
        reason=f"Banned by {mod} | spam",
        delete_message_seconds=172800,
    )
    mock_bot.stores.server_bans.insert_one.assert_awaited_once()
    assert "PES1UG21CS001" in interaction.followup.send.await_args.kwargs["embed"].description
    interaction.followup.send.assert_awaited()
    mock_bot.config.mod_logs_channel.send.assert_awaited()


async def test_ban_self_and_bot_targets_blocked(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    guild = _ban_guild(None)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    await get_callback(cmd.ban)(cmd, interaction, mod)
    assert "yourself" in interaction.followup.send.await_args.kwargs["content"]

    this_bot = member_factory(user_id=7, bot=True)
    mock_bot.user.id = this_bot.id
    await get_callback(cmd.ban)(cmd, interaction, this_bot)
    assert interaction.followup.send.await_args.kwargs["content"] == "Nope, not doing that again."

    another_bot = member_factory(user_id=8, bot=True)
    await get_callback(cmd.ban)(cmd, interaction, another_bot)
    assert interaction.followup.send.await_args.kwargs["content"] == "Nope, not doing that again."

    guild.ban.assert_not_awaited()


async def test_ban_invalid_reason_and_days(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2)
    guild = _ban_guild(target)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild

    await get_callback(cmd.ban)(cmd, interaction, target, "", 0)
    assert "1 and 400" in interaction.followup.send.await_args.kwargs["content"]

    await get_callback(cmd.ban)(cmd, interaction, target, "x" * 401, 0)
    assert "1 and 400" in interaction.followup.send.await_args.kwargs["content"]

    await get_callback(cmd.ban)(cmd, interaction, target, "spam", 8)
    assert "0 and 7" in interaction.followup.send.await_args.kwargs["content"]

    await get_callback(cmd.ban)(cmd, interaction, target, "spam", -1)
    assert "0 and 7" in interaction.followup.send.await_args.kwargs["content"]

    guild.ban.assert_not_awaited()


async def test_ban_protected_member(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[mock_bot.config.mod_role])
    guild = _ban_guild(target)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(return_value=None)

    await get_callback(cmd.ban)(cmd, interaction, target)
    content = interaction.followup.send.await_args.kwargs.get("content", "")
    assert interaction.followup.send.await_args.kwargs.get("ephemeral") is True
    assert "admin/mod" in content
    guild.ban.assert_not_awaited()


async def test_ban_left_server_skips_dm(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2)
    guild = _ban_guild(None)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(return_value=None)
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    await get_callback(cmd.ban)(cmd, interaction, target, "spam", 1)

    target.send.assert_not_awaited()
    guild.ban.assert_awaited_once_with(
        target,
        reason=f"Banned by {mod} | spam",
        delete_message_seconds=86400,
    )
    interaction.followup.send.assert_awaited()


async def test_ban_mod_log_failure_still_succeeds(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _ban_guild(target)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(return_value=None)
    mock_bot.config.mod_logs_channel.send = AsyncMock(
        side_effect=discord.HTTPException(MagicMock(), "boom"),
    )

    await get_callback(cmd.ban)(cmd, interaction, target, "spam")

    guild.ban.assert_awaited()
    interaction.followup.send.assert_awaited()


async def test_ban_linked_user_records_prn(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _ban_guild(target)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(
        return_value=Link(discord_user_id="2", prn="PES1UG21CS001"),
    )
    mock_bot.stores.server_bans.insert_one = AsyncMock()
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    await get_callback(cmd.ban)(cmd, interaction, target, "spam")

    guild.ban.assert_awaited()
    mock_bot.stores.links.find_one.assert_awaited_once_with(discord_user_id="2")
    mock_bot.stores.server_bans.insert_one.assert_awaited_once()
    ban = mock_bot.stores.server_bans.insert_one.await_args.args[0]
    assert isinstance(ban, ServerBan)
    assert ban.prn == "PES1UG21CS001"
    assert ban.discord_user_id == "2"
    assert ban.reason == "spam"


async def test_ban_unlinked_user_skips_identity_ban(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _ban_guild(target)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(return_value=None)
    mock_bot.stores.server_bans.insert_one = AsyncMock()
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    await get_callback(cmd.ban)(cmd, interaction, target, "spam")

    guild.ban.assert_awaited()
    mock_bot.stores.server_bans.insert_one.assert_not_called()
    interaction.followup.send.assert_awaited()


async def test_ban_repeat_records_idempotently(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _ban_guild(target)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(
        return_value=Link(discord_user_id="2", prn="PES1UG21CS001"),
    )
    mock_bot.stores.server_bans.insert_one = AsyncMock()
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    await get_callback(cmd.ban)(cmd, interaction, target, "spam")

    guild.ban.assert_awaited()
    mock_bot.stores.server_bans.insert_one.assert_awaited_once()
    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert "PES1UG21CS001" in embed.description


async def test_ban_dm_closed_still_bans(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _ban_guild(target)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(return_value=None)
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    with patch("src.cogs.mod.commands.ug.send_dm_safely", AsyncMock(return_value=False)) as send_dm_safely:
        await get_callback(cmd.ban)(cmd, interaction, target, "spam")

    send_dm_safely.assert_awaited_once_with(target, content="You have been banned from **PESU**\nReason: spam")
    guild.ban.assert_awaited()
    interaction.followup.send.assert_awaited()


async def test_ban_lookup_failure_blocks_ban(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _ban_guild(target)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(side_effect=PyMongoError("db down"))

    with pytest.raises(PyMongoError):
        await get_callback(cmd.ban)(cmd, interaction, target, "spam")

    guild.ban.assert_not_awaited()


async def test_ban_unexpected_lookup_exception_propagates(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _ban_guild(target)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(side_effect=RuntimeError("unexpected failure"))
    mock_bot.stores.server_bans.insert_one = AsyncMock()

    with pytest.raises(RuntimeError, match="unexpected failure"):
        await get_callback(cmd.ban)(cmd, interaction, target, "spam")

    guild.ban.assert_not_awaited()
    mock_bot.stores.server_bans.insert_one.assert_not_called()
    interaction.followup.send.assert_not_called()


async def test_ban_identity_persist_failure_notifies_coherently(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _ban_guild(target)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(
        return_value=Link(discord_user_id="2", prn="PES1UG21CS001"),
    )
    mock_bot.stores.server_bans.insert_one = AsyncMock(side_effect=PyMongoError("db down"))
    mock_bot.stores.pending_server_bans.replace_current = AsyncMock()
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    await get_callback(cmd.ban)(cmd, interaction, target, "spam")

    guild.ban.assert_awaited()
    mock_bot.stores.pending_server_bans.replace_current.assert_awaited_once()
    pending = mock_bot.stores.pending_server_bans.replace_current.await_args.args[0]
    assert pending.op == "ban"
    assert pending.prn == "PES1UG21CS001"
    calls = interaction.followup.send.await_args_list
    assert len(calls) == 1
    result = calls[0].kwargs
    assert result.get("ephemeral", False) is False
    description = result["embed"].description
    assert "was banned by" in description
    assert "FAILED to persist" in description
    assert "PES1UG21CS001" in description
    assert "may NOT" in description
    assert "Manual recovery required" in description
    assert "successfully recorded" not in description


async def test_ban_discord_failure_records_nothing(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _ban_guild(target)
    guild.ban = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no perms"))
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(
        return_value=Link(discord_user_id="2", prn="PES1UG21CS001"),
    )
    mock_bot.stores.server_bans.insert_one = AsyncMock()

    with pytest.raises(discord.Forbidden):
        await get_callback(cmd.ban)(cmd, interaction, target, "spam")

    mock_bot.stores.server_bans.insert_one.assert_not_called()


async def test_ban_malformed_link_record_fails_closed(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _ban_guild(target)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(side_effect=KeyError("prn"))
    mock_bot.stores.server_bans.insert_one = AsyncMock()
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    await get_callback(cmd.ban)(cmd, interaction, target, "spam")

    guild.ban.assert_not_awaited()
    mock_bot.stores.server_bans.insert_one.assert_not_called()
    calls = interaction.followup.send.await_args_list
    assert len(calls) == 1
    failure = calls[0].kwargs
    assert failure.get("ephemeral") is True
    assert "NOT performed" in failure["content"]
    assert "malformed" in failure["content"]
    assert "remains unbanned" in failure["content"]


async def test_ban_whitespace_prn_fails_closed(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _ban_guild(target)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(
        return_value=Link(discord_user_id="2", prn="   "),
    )
    mock_bot.stores.server_bans.insert_one = AsyncMock()
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    await get_callback(cmd.ban)(cmd, interaction, target, "spam")

    guild.ban.assert_not_awaited()
    mock_bot.stores.server_bans.insert_one.assert_not_called()
    calls = interaction.followup.send.await_args_list
    assert len(calls) == 1
    assert "NOT performed" in calls[0].kwargs["content"]


async def test_ban_concurrent_duplicate_treated_as_recorded(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _ban_guild(target)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(
        return_value=Link(discord_user_id="2", prn="PES1UG21CS001"),
    )
    mock_bot.stores.server_bans.insert_one = AsyncMock(side_effect=DuplicateKeyError("dup"))
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    await get_callback(cmd.ban)(cmd, interaction, target, "spam")

    guild.ban.assert_awaited()
    calls = interaction.followup.send.await_args_list
    assert len(calls) == 1
    description = calls[0].kwargs["embed"].description
    assert "PES1UG21CS001" in description
    assert "FAILED" not in description


async def test_unban_success_removes_identity(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _unban_guild(banned=True)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(
        return_value=Link(discord_user_id="2", prn=" pes1ug21cs001 "),
    )
    mock_bot.stores.server_bans.remove_ban_for_user = AsyncMock(return_value=True)
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    await get_callback(cmd.unban)(cmd, interaction, target, "appeal")

    guild.unban.assert_awaited_once_with(target, reason=f"Unbanned by {mod} | appeal")
    mock_bot.stores.server_bans.remove_ban_for_user.assert_awaited_once_with("PES1UG21CS001", "2")
    calls = interaction.followup.send.await_args_list
    assert len(calls) == 1
    description = calls[0].kwargs["embed"].description
    assert "was unbanned by" in description
    assert "removed" in description
    assert "PES1UG21CS001" in description
    mock_bot.config.mod_logs_channel.send.assert_awaited()


async def test_unban_not_banned_reports_cleanly(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _unban_guild(banned=False)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(return_value=None)
    mock_bot.stores.server_bans.remove_ban_for_user = AsyncMock()

    await get_callback(cmd.unban)(cmd, interaction, target)

    guild.unban.assert_not_called()
    mock_bot.stores.server_bans.remove_ban_for_user.assert_not_called()
    calls = interaction.followup.send.await_args_list
    assert len(calls) == 1
    description = calls[0].kwargs["embed"].description
    assert "was not Discord-banned" in description
    assert "none present" in description


async def test_unban_not_banned_clears_stale_identity(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _unban_guild(banned=False)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(
        return_value=Link(discord_user_id="2", prn="PES1UG21CS001"),
    )
    mock_bot.stores.server_bans.remove_ban_for_user = AsyncMock(return_value=True)

    await get_callback(cmd.unban)(cmd, interaction, target)

    guild.unban.assert_not_called()
    mock_bot.stores.server_bans.remove_ban_for_user.assert_awaited_once_with("PES1UG21CS001", "2")
    description = interaction.followup.send.await_args.kwargs["embed"].description
    assert "was not Discord-banned" in description
    assert "removed" in description


async def test_unban_discord_failure_preserves_identity(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _unban_guild(banned=True)
    guild.unban = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no perms"))
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(
        return_value=Link(discord_user_id="2", prn="PES1UG21CS001"),
    )
    mock_bot.stores.server_bans.remove_ban_for_user = AsyncMock()

    with pytest.raises(discord.Forbidden):
        await get_callback(cmd.unban)(cmd, interaction, target)

    mock_bot.stores.server_bans.remove_ban_for_user.assert_not_called()


async def test_unban_removal_failure_reports_partial(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _unban_guild(banned=True)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(
        return_value=Link(discord_user_id="2", prn="PES1UG21CS001"),
    )
    mock_bot.stores.server_bans.remove_ban_for_user = AsyncMock(side_effect=PyMongoError("db down"))
    mock_bot.stores.pending_server_bans.replace_current = AsyncMock()
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    await get_callback(cmd.unban)(cmd, interaction, target)

    guild.unban.assert_awaited()
    mock_bot.stores.pending_server_bans.replace_current.assert_awaited_once()
    pending = mock_bot.stores.pending_server_bans.replace_current.await_args.args[0]
    assert pending.op == "unban"
    assert pending.prn == "PES1UG21CS001"
    calls = interaction.followup.send.await_args_list
    assert len(calls) == 1
    description = calls[0].kwargs["embed"].description
    assert "was unbanned by" in description
    assert "FAILED to remove" in description
    assert "PES1UG21CS001" in description


async def test_unban_self_bot_owner_blocked(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    guild = _unban_guild(banned=True)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.user.id = 7

    await get_callback(cmd.unban)(cmd, interaction, mod)
    assert "yourself" in interaction.followup.send.await_args.kwargs["content"]

    await get_callback(cmd.unban)(cmd, interaction, member_factory(user_id=7))
    assert "myself" in interaction.followup.send.await_args.kwargs["content"]

    await get_callback(cmd.unban)(cmd, interaction, member_factory(user_id=999))
    assert "owner" in interaction.followup.send.await_args.kwargs["content"]

    guild.unban.assert_not_called()
    guild.fetch_ban.assert_not_called()


async def test_unban_malformed_link_proceeds_with_warning(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _unban_guild(banned=True)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(side_effect=KeyError("prn"))
    mock_bot.stores.server_bans.remove_ban_for_user = AsyncMock()

    await get_callback(cmd.unban)(cmd, interaction, target)

    guild.unban.assert_awaited()
    mock_bot.stores.server_bans.remove_ban_for_user.assert_not_called()
    calls = interaction.followup.send.await_args_list
    assert len(calls) == 1
    description = calls[0].kwargs["embed"].description
    assert "was unbanned by" in description
    assert "UNKNOWN" in description


async def test_unban_invalid_reason(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _unban_guild(banned=True)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild

    await get_callback(cmd.unban)(cmd, interaction, target, "")

    assert "1 and 400" in interaction.followup.send.await_args.kwargs["content"]
    guild.fetch_ban.assert_not_called()
    guild.unban.assert_not_called()


async def test_unban_mod_log_failure_still_succeeds(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _unban_guild(banned=True)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(return_value=None)
    mock_bot.config.mod_logs_channel.send = AsyncMock(
        side_effect=discord.HTTPException(MagicMock(), "boom"),
    )

    await get_callback(cmd.unban)(cmd, interaction, target)

    guild.unban.assert_awaited()
    interaction.followup.send.assert_awaited()


async def test_unban_already_removed_identity(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _unban_guild(banned=True)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(
        return_value=Link(discord_user_id="2", prn="PES1UG21CS001"),
    )
    mock_bot.stores.server_bans.remove_ban_for_user = AsyncMock(return_value=False)

    await get_callback(cmd.unban)(cmd, interaction, target)

    guild.unban.assert_awaited()
    description = interaction.followup.send.await_args.kwargs["embed"].description
    assert "was unbanned by" in description
    assert "none present" in description


async def test_ban_identity_persist_failure_pending_also_fails(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    guild = _ban_guild(target)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild
    mock_bot.stores.links.find_one = AsyncMock(
        return_value=Link(discord_user_id="2", prn="PES1UG21CS001"),
    )
    mock_bot.stores.server_bans.insert_one = AsyncMock(side_effect=PyMongoError("db down"))
    mock_bot.stores.pending_server_bans.replace_current = AsyncMock(side_effect=PyMongoError("still down"))
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    await get_callback(cmd.ban)(cmd, interaction, target, "spam")

    guild.ban.assert_awaited()
    calls = interaction.followup.send.await_args_list
    assert len(calls) == 1
    assert "FAILED to persist" in calls[0].kwargs["embed"].description


async def test_ban_unban_reban_lifecycle(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    interaction = interaction_factory(user=mod)
    mock_bot.config.mod_logs_channel.send = AsyncMock()
    link = Link(discord_user_id="2", prn="PES1UG21CS001")

    # BAN → identity recorded.
    ban_guild = _ban_guild(target)
    interaction.guild = ban_guild
    mock_bot.stores.links.find_one = AsyncMock(return_value=link)
    mock_bot.stores.server_bans.insert_one = AsyncMock()
    await get_callback(cmd.ban)(cmd, interaction, target, "spam")
    ban_guild.ban.assert_awaited()
    mock_bot.stores.server_bans.insert_one.assert_awaited_once()

    # UNBAN → Discord unbanned + identity removed.
    unban_guild = _unban_guild(banned=True)
    interaction.guild = unban_guild
    mock_bot.stores.server_bans.remove_ban_for_user = AsyncMock(return_value=True)
    await get_callback(cmd.unban)(cmd, interaction, target, "appeal")
    unban_guild.unban.assert_awaited()
    mock_bot.stores.server_bans.remove_ban_for_user.assert_awaited_once_with("PES1UG21CS001", "2")

    # REBAN → identity recorded again with no stale state in the way.
    reban_guild = _ban_guild(target)
    interaction.guild = reban_guild
    await get_callback(cmd.ban)(cmd, interaction, target, "again")
    reban_guild.ban.assert_awaited()
    assert mock_bot.stores.server_bans.insert_one.await_count == 2
