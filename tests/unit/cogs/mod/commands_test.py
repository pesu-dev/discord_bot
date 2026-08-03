from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from discord.ext import commands

from src.cogs.mod.commands import ModCommands
from src.cogs.mod.helpers import ModHelpers
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


async def test_handle_ban_message_link(
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

    found = await helpers._handle_ban_message_link(interaction, "https://discord.com/channels/1/2/999")
    assert found is member

    channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "x"))
    assert await helpers._handle_ban_message_link(interaction, "x/1") is None

    channel.fetch_message = AsyncMock(return_value=msg)
    mock_bot.anon_cache = {}
    assert await helpers._handle_ban_message_link(interaction, "x/999") is None


async def test_apply_anon_ban_dm_closed(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    mock_bot.stores.anonbans.exists = AsyncMock(return_value=False)
    mock_bot.stores.anonbans.insert_one = AsyncMock()
    interaction = interaction_factory()
    with patch("src.utils.general.send_dm_safely", AsyncMock(return_value=False)):
        await helpers._apply_anon_ban(interaction, member_factory(), time=None, reason="x", message_link="https://x")
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
