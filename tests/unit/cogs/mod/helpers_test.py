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


async def test_create_and_store_ban_permanent(mock_bot: MagicMock) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    mock_bot.stores.anon_bans.insert_one = AsyncMock()
    assert await helpers._create_and_store_ban("7", "spam") is None
    ban = mock_bot.stores.anon_bans.insert_one.await_args.args[0]
    assert isinstance(ban, AnonBan)
    assert ban.discord_user_id == "7"
    assert ban.reason == "spam"
    assert ban.unbanned_at is None


async def test_apply_anon_ban_already_banned(
    mock_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    mock_bot.stores.anon_bans.has_active = AsyncMock(return_value=True)
    interaction = interaction_factory()
    await helpers._apply_anon_ban(interaction, member_factory(), reason="x")
    assert "already banned" in interaction.followup.send.await_args.kwargs["content"]


async def test_apply_anon_ban_success(
    mock_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    mock_bot.stores.anon_bans.has_active = AsyncMock(return_value=False)
    mock_bot.stores.anon_bans.insert_one = AsyncMock()
    member = member_factory()
    interaction = interaction_factory()

    with patch("src.utils.general.send_dm_safely", AsyncMock(return_value=True)):
        await helpers._apply_anon_ban(interaction, member, reason="abuse")

    assert any("banned from anon" in (c.kwargs.get("content") or "") for c in interaction.followup.send.await_args_list)


async def test_apply_anon_mute_already_muted(
    mock_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    mock_bot.stores.anon_bans.has_active = AsyncMock(return_value=False)
    mock_bot.stores.anon_mutes.has_active = AsyncMock(return_value=True)
    interaction = interaction_factory()
    await helpers._apply_anon_mute(interaction, member_factory(), time="1h", reason="x")
    assert "already muted" in interaction.followup.send.await_args.kwargs["content"]


async def test_apply_anon_mute_invalid_time(
    mock_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    mock_bot.stores.anon_bans.has_active = AsyncMock(return_value=False)
    mock_bot.stores.anon_mutes.has_active = AsyncMock(return_value=False)
    mock_bot.stores.anon_mutes.insert_one = AsyncMock()
    interaction = interaction_factory()
    await helpers._apply_anon_mute(interaction, member_factory(), time="5s", reason="x")
    mock_bot.stores.anon_mutes.insert_one.assert_not_called()


async def test_apply_anon_mute_dm_closed(
    mock_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    mock_bot.stores.anon_bans.has_active = AsyncMock(return_value=False)
    mock_bot.stores.anon_mutes.has_active = AsyncMock(return_value=False)
    mock_bot.stores.anon_mutes.insert_one = AsyncMock()
    interaction = interaction_factory()
    with patch("src.utils.general.send_dm_safely", AsyncMock(return_value=False)):
        await helpers._apply_anon_mute(interaction, member_factory(), time="1h", reason="spam")
    assert any("DMs were closed" in (c.kwargs.get("content") or "") for c in interaction.followup.send.await_args_list)


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
        return_value=Link(discord_user_id="1", prn="PES1UG21CS001", linked_at=datetime.now(UTC))
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
        discord_user_id=str(user_id),
        discord_channel_id=channel_id,
        moderator_discord_user_id="1",
        mute_time=now - timedelta(hours=1),
        original_unmute_time=now - timedelta(seconds=1),
        reason="test",
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
    assert "unmuted_at" in kwargs
    mock_bot.stores.mutes.mark_unmuted.assert_awaited_once_with(mute.id, unmuted_at=kwargs["unmuted_at"])


async def test_mute_loop_skips_missing_id(mock_bot: MagicMock) -> None:
    from src.cogs.mod import SlashMod

    with patch.object(
        SlashMod,
        "__init__",
        lambda self, client: setattr(self, "client", client) or setattr(self, "tasks", []),
    ):
        cog = SlashMod(mock_bot)

    mute = _expired_mute(mute_id=ObjectId(), user_id=99, channel_id=1)
    mute.id = None
    mock_bot.stores.mutes.find_expired = AsyncMock(return_value=[mute])
    mock_bot.stores.mutes.mark_unmuted = AsyncMock()
    mock_bot.config.guild = MagicMock()
    mock_bot.config.guild.fetch_member = AsyncMock()

    await SlashMod.check_mutes_loop(cog)
    mock_bot.stores.mutes.mark_unmuted.assert_not_called()
    mock_bot.config.guild.fetch_member.assert_not_called()


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
    assert "unmuted_at" in kwargs
    mock_bot.stores.mutes.mark_unmuted.assert_awaited_once_with(mute.id, unmuted_at=kwargs["unmuted_at"])


async def test_link_info_missing_prn(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    commands = LinkCommands()
    commands.client = mock_bot
    mock_bot.stores.links.find_one = AsyncMock(return_value=Link(discord_user_id="1", prn=""))
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


async def test_handle_ban_link_no_guild(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    helpers = _Helpers()
    helpers.client = mock_bot
    interaction = interaction_factory()
    interaction.guild = None
    assert await helpers._handle_anon_message_link(interaction, "x/1") is None


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


async def test_slash_mod_skips_start_when_running(mock_bot: MagicMock) -> None:
    from discord.ext import tasks

    from src.cogs.mod import SlashMod

    def is_running_skip_start(self: object) -> bool:
        if not hasattr(self, "_last_iteration"):
            return False
        return True

    with (
        patch.object(tasks.Loop, "is_running", is_running_skip_start),
        patch.object(tasks.Loop, "start") as start,
        patch.object(tasks.Loop, "cancel"),
    ):
        SlashMod(mock_bot)
    start.assert_not_called()
