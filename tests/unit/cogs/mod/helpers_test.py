from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from bson import ObjectId

from src.cogs.mod.helpers import ModHelpers
from src.cogs.mod.link import LinkCommands
from src.data.mongo import AnonBan, Link, Mute
from tests.helpers import get_callback

if TYPE_CHECKING:
    from tests.conftest import InteractionFactory, MemberFactory


class _Helpers(ModHelpers):
    pass


class _DeleteResult:
    def __init__(self, deleted_count: int) -> None:
        self.deleted_count = deleted_count


async def test_check_user_anon_ban(mock_bot: MagicMock) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    mock_bot.stores.anonbans.exists = AsyncMock(return_value=True)
    assert await helpers._check_user_anon_ban("1") is True


async def test_validate_and_parse_time_too_short(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    interaction = interaction_factory()
    assert await helpers._validate_and_parse_time(interaction, "5s") is None
    interaction.followup.send.assert_awaited()


async def test_validate_and_parse_time_invalid(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    interaction = interaction_factory()
    assert await helpers._validate_and_parse_time(interaction, "nope") is None


async def test_validate_and_parse_time_ok(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    interaction = interaction_factory()
    assert await helpers._validate_and_parse_time(interaction, "1h") == 3600


def test_find_user_from_message(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    member = member_factory(user_id=42)
    mock_bot.anon_cache = {"42": [{"message_id": "999", "timestamp": datetime.now(UTC)}]}
    guild = MagicMock(spec=discord.Guild)
    guild.get_member = MagicMock(return_value=member)
    assert helpers._find_user_from_message("999", guild) is member
    assert helpers._find_user_from_message("111", guild) is None


async def test_create_and_store_ban_timed(mock_bot: MagicMock) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    mock_bot.stores.anonbans.insert_one = AsyncMock()
    expiry = await helpers._create_and_store_ban("7", "spam", "1h")
    assert expiry != "Permanent"
    ban = mock_bot.stores.anonbans.insert_one.await_args.args[0]
    assert isinstance(ban, AnonBan)
    assert ban.active is True
    assert ban.expires_at is not None


async def test_create_and_store_ban_permanent(mock_bot: MagicMock) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    mock_bot.stores.anonbans.insert_one = AsyncMock()
    assert await helpers._create_and_store_ban("7", "spam") == "Permanent"


async def test_apply_anon_ban_already_banned(
    mock_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    mock_bot.stores.anonbans.exists = AsyncMock(return_value=True)
    interaction = interaction_factory()
    await helpers._apply_anon_ban(interaction, member_factory(), time=None, reason="x")
    assert "already banned" in interaction.followup.send.await_args.kwargs["content"]


async def test_apply_anon_ban_success(
    mock_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    mock_bot.stores.anonbans.exists = AsyncMock(return_value=False)
    mock_bot.stores.anonbans.insert_one = AsyncMock()
    member = member_factory()
    interaction = interaction_factory()

    with patch("src.utils.general.send_dm_safely", AsyncMock(return_value=True)):
        await helpers._apply_anon_ban(interaction, member, time="1d", reason="abuse")

    assert any("banned from anon" in (c.kwargs.get("content") or "") for c in interaction.followup.send.await_args_list)


async def test_mod_link_info_not_linked(
    mock_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    commands = LinkCommands()
    commands.client = mock_bot
    mock_bot.stores.links.find_one = AsyncMock(return_value=None)
    interaction = interaction_factory()
    await get_callback(commands.mod_link_info)(commands, interaction, member_factory())
    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert any(f.name == "Status" for f in embed.fields)


async def test_mod_link_info_with_prn(
    mock_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    commands = LinkCommands()
    commands.client = mock_bot
    mock_bot.stores.links.find_one = AsyncMock(
        return_value=Link(user_id="1", prn="PES1UG21CS001", linked_at=datetime.now(UTC))
    )
    interaction = interaction_factory()
    await get_callback(commands.mod_link_info)(commands, interaction, member_factory())
    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert any(f.name == "PRN" for f in embed.fields)


async def test_mod_link_disconnect_not_linked(
    mock_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    commands = LinkCommands()
    commands.client = mock_bot
    mock_bot.stores.links.delete_one = AsyncMock(return_value=_DeleteResult(0))
    interaction = interaction_factory()
    await get_callback(commands.mod_link_disconnect)(commands, interaction, member_factory())
    assert "not linked" in interaction.followup.send.await_args.kwargs["content"]


async def test_mod_link_disconnect_strips_roles(
    mock_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    commands = LinkCommands()
    commands.client = mock_bot
    guild = MagicMock(spec=discord.Guild)
    guild.id = 742797665301168220
    everyone = MagicMock(spec=discord.Role)
    everyone.id = guild.id
    extra = MagicMock(spec=discord.Role)
    extra.id = 123
    user = member_factory(user_id=77, roles=[everyone, extra, mock_bot.config.linked_role])
    interaction = interaction_factory(guild=guild)
    interaction.guild = guild
    mock_bot.stores.links.delete_one = AsyncMock(return_value=_DeleteResult(1))

    await get_callback(commands.mod_link_disconnect)(commands, interaction, user)
    user.remove_roles.assert_awaited()
    user.add_roles.assert_awaited_with(mock_bot.config.just_joined_role)
    interaction.followup.send.assert_awaited()


def _expired_mute(*, mute_id: ObjectId, user_id: int, channel_id: int) -> Mute:
    now = datetime.now(UTC)
    return Mute(
        id=mute_id,
        user_id=user_id,
        channel_id=channel_id,
        moderator_id=1,
        mute_time=now - timedelta(hours=1),
        unmute_time=now - timedelta(seconds=1),
        reason="test",
        active=True,
        is_self_mute=False,
    )


async def test_mute_loop_marks_inactive_when_member_left(mock_bot: MagicMock) -> None:
    from src.cogs.mod import SlashMod

    with patch.object(
        SlashMod,
        "__init__",
        lambda self, client: setattr(self, "client", client) or setattr(self, "tasks", []),
    ):
        cog = SlashMod(mock_bot)

    mute = _expired_mute(mute_id=ObjectId(), user_id=99, channel_id=1)
    mock_bot.stores.mutes.find_expired = AsyncMock(return_value=[mute])
    mock_bot.stores.mutes.mark_unmuted = AsyncMock()
    mock_bot.config.guild = MagicMock()
    mock_bot.config.guild.fetch_member = AsyncMock(side_effect=discord.NotFound(MagicMock(), "gone"))

    await SlashMod.check_mutes_loop(cog)
    kwargs = mock_bot.stores.mutes.mark_unmuted.await_args.kwargs
    assert kwargs["unmute_type"] == "auto_member_left"


async def test_mute_loop_unmutes_member(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    from src.cogs.mod import SlashMod

    with patch.object(
        SlashMod,
        "__init__",
        lambda self, client: setattr(self, "client", client) or setattr(self, "tasks", []),
    ):
        cog = SlashMod(mock_bot)

    mute = _expired_mute(mute_id=ObjectId(), user_id=50, channel_id=2001)
    member = member_factory(user_id=50, roles=[mock_bot.config.muted_role])
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()

    mock_bot.stores.mutes.find_expired = AsyncMock(return_value=[mute])
    mock_bot.stores.mutes.mark_unmuted = AsyncMock()
    mock_bot.config.guild = MagicMock()
    mock_bot.config.guild.fetch_member = AsyncMock(return_value=member)
    mock_bot.config.guild.get_channel = MagicMock(return_value=channel)
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    await SlashMod.check_mutes_loop(cog)
    member.remove_roles.assert_awaited()
    kwargs = mock_bot.stores.mutes.mark_unmuted.await_args.kwargs
    assert kwargs["unmute_type"] == "loop_auto"


async def test_link_info_missing_prn(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    commands = LinkCommands()
    commands.client = mock_bot
    mock_bot.stores.links.find_one = AsyncMock(return_value=Link(user_id="1", prn=""))
    interaction = interaction_factory()
    await get_callback(commands.mod_link_info)(commands, interaction, member_factory())
    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert any(f.name == "Error" for f in embed.fields)


async def test_link_disconnect_forbidden(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    commands = LinkCommands()
    commands.client = mock_bot
    guild = MagicMock(spec=discord.Guild)
    guild.id = 742797665301168220
    user = member_factory(roles=[mock_bot.config.linked_role])
    user.remove_roles = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no"))
    interaction = interaction_factory(guild=guild)
    interaction.guild = guild
    mock_bot.stores.links.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    await get_callback(commands.mod_link_disconnect)(commands, interaction, user)
    assert "unable to remove roles" in interaction.followup.send.await_args.kwargs["content"]


async def test_mute_loop_before_and_remove_error(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    from src.cogs.mod import SlashMod

    with patch.object(
        SlashMod,
        "__init__",
        lambda self, client: setattr(self, "client", client) or setattr(self, "tasks", []),
    ):
        cog = SlashMod(mock_bot)

    mock_bot.wait_until_ready = AsyncMock()
    await SlashMod.before_check_mutes_loop(cog)
    mock_bot.wait_until_ready.assert_awaited()

    mute = _expired_mute(mute_id=ObjectId(), user_id=50, channel_id=2001)
    member = member_factory(user_id=50, roles=[mock_bot.config.muted_role])
    member.remove_roles = AsyncMock(side_effect=RuntimeError("perm"))
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "fail"))

    mock_bot.stores.mutes.find_expired = AsyncMock(return_value=[mute])
    mock_bot.stores.mutes.mark_unmuted = AsyncMock()
    mock_bot.config.guild = MagicMock()
    mock_bot.config.guild.fetch_member = AsyncMock(return_value=member)
    mock_bot.config.guild.get_channel = MagicMock(return_value=channel)
    mock_bot.config.bot_logs_channel.send = AsyncMock()
    mock_bot.config.mod_logs_channel.send = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "fail"))

    await SlashMod.check_mutes_loop(cog)
    mock_bot.config.bot_logs_channel.send.assert_awaited()


async def test_mute_loop_skips_non_text_channel(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    from src.cogs.mod import SlashMod

    with patch.object(
        SlashMod,
        "__init__",
        lambda self, client: setattr(self, "client", client) or setattr(self, "tasks", []),
    ):
        cog = SlashMod(mock_bot)

    mute = _expired_mute(mute_id=ObjectId(), user_id=50, channel_id=2001)
    member = member_factory(user_id=50, roles=[])

    mock_bot.stores.mutes.find_expired = AsyncMock(return_value=[mute])
    mock_bot.stores.mutes.mark_unmuted = AsyncMock()
    mock_bot.config.guild = MagicMock()
    mock_bot.config.guild.fetch_member = AsyncMock(return_value=member)
    mock_bot.config.guild.get_channel = MagicMock(return_value=MagicMock())
    mock_bot.config.mod_logs_channel.send = AsyncMock()
    await SlashMod.check_mutes_loop(cog)
    mock_bot.stores.mutes.mark_unmuted.assert_awaited()


async def test_apply_anon_ban_invalid_time(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    mock_bot.stores.anonbans.exists = AsyncMock(return_value=False)
    interaction = interaction_factory()
    await helpers._apply_anon_ban(interaction, member_factory(), time="bad", reason="x")
    assert "proper amount of time" in interaction.followup.send.await_args.kwargs["content"]


async def test_handle_ban_link_no_guild(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    interaction = interaction_factory()
    interaction.guild = None
    assert await helpers._handle_ban_message_link(interaction, "x/1") is None


async def test_slash_mod_lifecycle(mock_bot: MagicMock) -> None:
    from src.cogs.mod import SlashMod

    mock_bot.wait_until_ready = AsyncMock()
    with (
        patch("discord.ext.tasks.Loop.start"),
        patch("discord.ext.tasks.Loop.is_running", return_value=False),
        patch("discord.ext.tasks.Loop.cancel"),
    ):
        cog = SlashMod(mock_bot)
        assert cog.ctx_menu is not None
        await cog.cog_unload()
