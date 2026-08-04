from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from src.cogs.anon import SlashAnon
from src.cogs.mod.anon import AnonModCommands
from src.data.mongo import AnonBan, AnonMute
from tests.helpers import get_callback

if TYPE_CHECKING:
    from tests.conftest import InteractionFactory, MemberFactory


async def test_ban_anon_requires_exactly_one_target(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    interaction = interaction_factory()
    await get_callback(cmd.ban_anon)(cmd, interaction, member=None, link=None)
    assert "exactly one" in interaction.followup.send.await_args.kwargs["content"]


async def test_ban_anon_member(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    mock_bot.stores.anon_bans.has_active = AsyncMock(return_value=False)
    mock_bot.stores.anon_bans.insert_one = AsyncMock()
    interaction = interaction_factory()
    member = member_factory(user_id=44)
    with patch("src.utils.general.send_dm_safely", AsyncMock(return_value=True)):
        await get_callback(cmd.ban_anon)(cmd, interaction, member=member, link=None, reason="spam")
    mock_bot.stores.anon_bans.insert_one.assert_awaited()


async def test_user_unban_anon(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    mock_bot.stores.anon_bans.unban = AsyncMock(
        return_value=AnonBan(
            discord_user_id="1",
            reason="spam",
            banned_at=datetime.now(UTC),
        )
    )
    interaction = interaction_factory()
    member = member_factory()
    with patch("src.utils.general.send_dm_safely", AsyncMock(return_value=True)):
        await get_callback(cmd.user_unban_anon)(cmd, interaction, member)
    assert "unbanned" in interaction.followup.send.await_args.kwargs["content"].lower()


async def test_user_unban_anon_not_banned(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    mock_bot.stores.anon_bans.unban = AsyncMock(return_value=None)
    interaction = interaction_factory()
    await get_callback(cmd.user_unban_anon)(cmd, interaction, member_factory())
    assert "wasn't even anon-banned" in interaction.followup.send.await_args.kwargs["content"]


async def test_anon_ban_info(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    mock_bot.stores.anon_bans.find_active = AsyncMock(
        return_value=AnonBan(
            discord_user_id="1",
            reason="spam",
            banned_at=datetime.now(UTC),
        )
    )
    mock_bot.stores.anon_mutes.find_active = AsyncMock(return_value=None)
    interaction = interaction_factory()
    await get_callback(cmd.anon_ban_info)(cmd, interaction, member_factory())
    assert "embed" in interaction.followup.send.await_args.kwargs


async def test_anon_context_menu_ban(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    member = member_factory(user_id=88)
    mock_bot.anon_cache = {"88": [{"message_id": "123", "timestamp": datetime.now(UTC)}]}
    mock_bot.stores.anon_bans.has_active = AsyncMock(return_value=False)
    mock_bot.stores.anon_bans.insert_one = AsyncMock()
    guild = MagicMock()
    guild.id = 1
    guild.get_member = MagicMock(return_value=member)
    interaction = interaction_factory(guild=guild)
    interaction.guild = guild
    interaction.channel = MagicMock()
    interaction.channel.id = 2
    message = MagicMock()
    message.id = 123
    with patch("src.utils.general.send_dm_safely", AsyncMock(return_value=True)):
        await get_callback(cmd.anon_ban_from_context_menu)(cmd, interaction, message)
    mock_bot.stores.anon_bans.insert_one.assert_awaited()


async def test_anon_clear_cache_loop(mock_bot: MagicMock) -> None:
    with patch.object(
        SlashAnon,
        "__init__",
        lambda self, client: setattr(self, "client", client) or setattr(self, "tasks", []),
    ):
        cog = SlashAnon(mock_bot)

    old = datetime(2020, 1, 1, tzinfo=UTC)
    recent = datetime.now(UTC)
    mock_bot.anon_cache = {
        "1": [{"message_id": "a", "timestamp": old}, {"message_id": "b", "timestamp": recent}],
        "2": [{"message_id": "c", "timestamp": old}],
    }
    await SlashAnon.clear_anon_cache_loop(cog)
    assert mock_bot.anon_cache["1"][0]["message_id"] == "b"
    assert mock_bot.anon_cache["2"] == []


async def test_context_menu_already_banned_and_dm_fail(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    member = member_factory(user_id=88)
    mock_bot.anon_cache = {"88": [{"message_id": "123", "timestamp": datetime.now(UTC)}]}
    guild = MagicMock()
    guild.id = 1
    guild.get_member = MagicMock(return_value=member)
    interaction = interaction_factory(guild=guild)
    interaction.guild = guild
    interaction.channel = MagicMock(id=2)
    message = MagicMock(id=123)

    mock_bot.stores.anon_bans.has_active = AsyncMock(return_value=True)
    await get_callback(cmd.anon_ban_from_context_menu)(cmd, interaction, message)
    assert "already banned" in interaction.followup.send.await_args.kwargs["content"]

    mock_bot.stores.anon_bans.has_active = AsyncMock(return_value=False)
    mock_bot.stores.anon_bans.insert_one = AsyncMock()
    with patch("src.utils.general.send_dm_safely", AsyncMock(return_value=False)):
        await get_callback(cmd.anon_ban_from_context_menu)(cmd, interaction, message)
    assert "couldn't DM" in interaction.followup.send.await_args.kwargs["content"]


async def test_anon_ban_info_not_banned(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    mock_bot.stores.anon_bans.find_active = AsyncMock(return_value=None)
    mock_bot.stores.anon_mutes.find_active = AsyncMock(return_value=None)
    interaction = interaction_factory()
    await get_callback(cmd.anon_ban_info)(cmd, interaction, member_factory())
    assert "no active anon ban or mute" in interaction.followup.send.await_args.kwargs["content"]


async def test_unban_dm_closed(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    mock_bot.stores.anon_bans.unban = AsyncMock(
        return_value=AnonBan(
            discord_user_id="1",
            reason="spam",
            banned_at=datetime.now(UTC),
        )
    )
    interaction = interaction_factory()
    with patch("src.utils.general.send_dm_safely", AsyncMock(return_value=False)):
        await get_callback(cmd.user_unban_anon)(cmd, interaction, member_factory())
    assert any("DMs were closed" in (c.kwargs.get("content") or "") for c in interaction.followup.send.await_args_list)


async def test_ban_anon_via_link(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    member = member_factory(user_id=42)
    mock_bot.stores.anon_bans.has_active = AsyncMock(return_value=False)
    mock_bot.stores.anon_bans.insert_one = AsyncMock()
    interaction = interaction_factory()
    with (
        patch.object(cmd, "_handle_anon_message_link", AsyncMock(return_value=member)),
        patch("src.utils.general.send_dm_safely", AsyncMock(return_value=True)),
    ):
        await get_callback(cmd.ban_anon)(cmd, interaction, member=None, link="https://x/1")
    mock_bot.stores.anon_bans.insert_one.assert_awaited()


async def test_ban_anon_link_resolve_fails(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    mock_bot.stores.anon_bans.insert_one = AsyncMock()
    interaction = interaction_factory()
    with patch.object(cmd, "_handle_anon_message_link", AsyncMock(return_value=None)):
        await get_callback(cmd.ban_anon)(cmd, interaction, member=None, link="https://x/1")
    mock_bot.stores.anon_bans.insert_one.assert_not_called()


async def test_context_menu_not_anon(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    mock_bot.anon_cache = {}
    guild = MagicMock()
    guild.get_member = MagicMock(return_value=None)
    interaction = interaction_factory(guild=guild)
    interaction.guild = guild
    await get_callback(cmd.anon_ban_from_context_menu)(cmd, interaction, MagicMock(id=1))
    assert "wasn't an anon message" in interaction.followup.send.await_args.kwargs["content"]


async def test_mute_anon_success(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    mock_bot.stores.anon_bans.has_active = AsyncMock(return_value=False)
    mock_bot.stores.anon_mutes.has_active = AsyncMock(return_value=False)
    mock_bot.stores.anon_mutes.insert_one = AsyncMock()
    interaction = interaction_factory()
    member = member_factory(user_id=44)
    with patch("src.utils.general.send_dm_safely", AsyncMock(return_value=True)):
        await get_callback(cmd.mute_anon)(cmd, interaction, member=member, link=None, time="1h", reason="spam")
    mock_bot.stores.anon_mutes.insert_one.assert_awaited()


async def test_mute_anon_via_link(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    member = member_factory(user_id=42)
    mock_bot.stores.anon_bans.has_active = AsyncMock(return_value=False)
    mock_bot.stores.anon_mutes.has_active = AsyncMock(return_value=False)
    mock_bot.stores.anon_mutes.insert_one = AsyncMock()
    interaction = interaction_factory()
    with (
        patch.object(cmd, "_handle_anon_message_link", AsyncMock(return_value=member)),
        patch("src.utils.general.send_dm_safely", AsyncMock(return_value=True)),
    ):
        await get_callback(cmd.mute_anon)(cmd, interaction, member=None, link="https://x/1", time="1h")
    mock_bot.stores.anon_mutes.insert_one.assert_awaited()


async def test_mute_anon_requires_exactly_one_target(
    mock_bot: MagicMock, interaction_factory: InteractionFactory
) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    interaction = interaction_factory()
    await get_callback(cmd.mute_anon)(cmd, interaction, member=None, link=None, time="1h")
    assert "exactly one" in interaction.followup.send.await_args.kwargs["content"]


async def test_mute_anon_already_banned(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    mock_bot.stores.anon_bans.has_active = AsyncMock(return_value=True)
    interaction = interaction_factory()
    await get_callback(cmd.mute_anon)(cmd, interaction, member=member_factory(), link=None, time="1h")
    assert "permanently banned" in interaction.followup.send.await_args.kwargs["content"]


async def test_unmute_anon_success(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    mock_bot.stores.anon_mutes.unmute_user = AsyncMock(return_value=MagicMock(modified_count=1))
    interaction = interaction_factory()
    with patch("src.utils.general.send_dm_safely", AsyncMock(return_value=True)):
        await get_callback(cmd.unmute_anon)(cmd, interaction, member_factory())
    mock_bot.stores.anon_mutes.unmute_user.assert_awaited()


async def test_unmute_anon_not_muted(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    mock_bot.stores.anon_mutes.unmute_user = AsyncMock(return_value=MagicMock(modified_count=0))
    interaction = interaction_factory()
    await get_callback(cmd.unmute_anon)(cmd, interaction, member_factory())
    assert "wasn't even anon-muted" in interaction.followup.send.await_args.kwargs["content"]


async def test_cleanup_stale_records_loop(mock_bot: MagicMock) -> None:
    from src.cogs.mod import SlashMod

    with patch.object(
        SlashMod,
        "__init__",
        lambda self, client: setattr(self, "client", client) or setattr(self, "tasks", []),
    ):
        cog = SlashMod(mock_bot)
    mock_bot.stores.mutes.delete_stale = AsyncMock()
    mock_bot.stores.anon_mutes.delete_stale = AsyncMock()
    mock_bot.stores.anon_bans.delete_stale = AsyncMock()
    await SlashMod.cleanup_stale_records_loop(cog)
    mock_bot.stores.mutes.delete_stale.assert_awaited()
    mock_bot.stores.anon_mutes.delete_stale.assert_awaited()
    mock_bot.stores.anon_bans.delete_stale.assert_awaited()


async def test_before_cleanup_stale_records_loop(mock_bot: MagicMock) -> None:
    from src.cogs.mod import SlashMod

    mock_bot.wait_until_ready = AsyncMock()
    with patch.object(
        SlashMod,
        "__init__",
        lambda self, client: setattr(self, "client", client) or setattr(self, "tasks", []),
    ):
        cog = SlashMod(mock_bot)
    await SlashMod.before_cleanup_stale_records_loop(cog)
    mock_bot.wait_until_ready.assert_awaited()


async def test_mute_anon_link_resolve_fails(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    mock_bot.stores.anon_mutes.insert_one = AsyncMock()
    interaction = interaction_factory()
    with patch.object(cmd, "_handle_anon_message_link", AsyncMock(return_value=None)):
        await get_callback(cmd.mute_anon)(cmd, interaction, member=None, link="https://x/1", time="1h")
    mock_bot.stores.anon_mutes.insert_one.assert_not_called()


async def test_unmute_anon_dm_closed(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    mock_bot.stores.anon_mutes.unmute_user = AsyncMock(return_value=MagicMock(modified_count=1))
    interaction = interaction_factory()
    with patch("src.utils.general.send_dm_safely", AsyncMock(return_value=False)):
        await get_callback(cmd.unmute_anon)(cmd, interaction, member_factory())
    assert any("DMs were closed" in (c.kwargs.get("content") or "") for c in interaction.followup.send.await_args_list)


async def test_anon_ban_info_with_mute(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonModCommands()
    cmd.client = mock_bot
    now = datetime.now(UTC)
    mock_bot.stores.anon_bans.find_active = AsyncMock(return_value=None)
    mock_bot.stores.anon_mutes.find_active = AsyncMock(
        return_value=AnonMute(
            discord_user_id="1",
            moderator_discord_user_id="2",
            muted_at=now,
            original_unmute_time=now,
            reason="noise",
        )
    )
    interaction = interaction_factory()
    await get_callback(cmd.anon_ban_info)(cmd, interaction, member_factory())
    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert any(f.name == "Mute Reason" for f in embed.fields)
