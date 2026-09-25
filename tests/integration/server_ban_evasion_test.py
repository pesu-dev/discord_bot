"""Integration tests for PRN-based ban evasion prevention (real MongoDB)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import discord
import httpx
import respx

from src.cogs.general.helpers import GeneralHelpers, LinkMessage
from src.cogs.mod.commands import ModCommands
from src.data.mongo import Link, ServerBan, Stores
from src.utils.config import Config
from tests.helpers import get_callback

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

    from tests.conftest import InteractionFactory, MemberFactory

AUTH_URL = Config.PESU_AUTH_URL
PROFILE = {
    "prn": "PES1202100001",
    "branch": "Computer Science and Engineering",
    "campus": "RR",
    "campusCode": 1,
}


def _ban_guild(target: MagicMock) -> MagicMock:
    guild = MagicMock()
    guild.name = "PESU"
    guild.owner_id = 999
    guild.get_member = MagicMock(return_value=target)
    guild.ban = AsyncMock()
    return guild


async def test_server_ban_persists_across_store_reinit(wired_bot: MagicMock, mongo_db: AsyncDatabase) -> None:
    await wired_bot.stores.server_bans.insert_one(
        ServerBan(
            prn="PES1202100001",
            discord_user_id="111111",
            reason="spam",
            banned_at=datetime.now(UTC),
        )
    )
    assert await wired_bot.stores.server_bans.has_active("PES1202100001") is True

    # Simulate a bot restart: fresh store objects over the same database.
    restarted = await Stores.create(mongo_db)
    assert await restarted.server_bans.has_active("PES1202100001") is True
    assert await restarted.server_bans.has_active("PES1202100002") is False


async def test_ban_linked_user_records_prn(
    wired_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    await wired_bot.stores.links.insert_one(
        Link(discord_user_id="222222", prn="PES1202100001", linked_at=datetime.now(UTC)),
    )

    cmd = ModCommands()
    cmd.client = wired_bot
    mod = member_factory(user_id=1, roles=[wired_bot.config.mod_role])
    target = member_factory(user_id=222222, roles=[])
    guild = _ban_guild(target)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild

    await get_callback(cmd.ban)(cmd, interaction, target, "spam")

    guild.ban.assert_awaited()
    assert await wired_bot.stores.server_bans.has_active("PES1202100001") is True
    ban = await wired_bot.stores.server_bans.find_one(prn="PES1202100001")
    assert ban is not None
    assert ban.discord_user_id == "222222"
    assert ban.reason == "spam"


async def test_ban_unlinked_user_records_nothing(
    wired_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    cmd = ModCommands()
    cmd.client = wired_bot
    mod = member_factory(user_id=1, roles=[wired_bot.config.mod_role])
    target = member_factory(user_id=333333, roles=[])
    guild = _ban_guild(target)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild

    await get_callback(cmd.ban)(cmd, interaction, target, "spam")

    guild.ban.assert_awaited()
    assert await wired_bot.stores.server_bans.has_active("PES1202100001") is False


@respx.mock
async def test_banned_prn_cannot_link_from_new_account(wired_bot: MagicMock, member_factory: MemberFactory) -> None:
    await wired_bot.stores.server_bans.insert_one(
        ServerBan(
            prn="PES1202100001",
            discord_user_id="111111",
            reason="spam",
            banned_at=datetime.now(UTC),
        )
    )
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json={"status": True, "profile": PROFILE}))

    helpers = GeneralHelpers()
    helpers.client = wired_bot
    helpers.cached_data = None
    new_account = member_factory(user_id=222222, roles=[])

    message, followup = await helpers.link_account(new_account, "PES1202100001", "secret")

    assert message == LinkMessage.PRN_BANNED
    assert followup is None
    assert await wired_bot.stores.links.exists(discord_user_id="222222") is False
    new_account.add_roles.assert_not_awaited()


@respx.mock
async def test_different_prn_links_despite_other_ban(wired_bot: MagicMock, member_factory: MemberFactory) -> None:
    await wired_bot.stores.server_bans.insert_one(
        ServerBan(
            prn="PES1202100001",
            discord_user_id="111111",
            reason="spam",
            banned_at=datetime.now(UTC),
        )
    )
    other = {**PROFILE, "prn": "PES1202100002"}
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json={"status": True, "profile": other}))

    helpers = GeneralHelpers()
    helpers.client = wired_bot
    helpers.cached_data = None
    member = member_factory(user_id=444444, roles=[wired_bot.config.just_joined_role])

    message, _ = await helpers.link_account(member, "PES1202100002", "secret")

    assert message == LinkMessage.SUCCESS
    assert await wired_bot.stores.links.exists(prn="PES1202100002") is True


def _unban_guild(*, banned: bool = True) -> MagicMock:
    guild = MagicMock()
    guild.name = "PESU"
    guild.owner_id = 999
    if banned:
        guild.fetch_ban = AsyncMock(return_value=MagicMock())
    else:
        guild.fetch_ban = AsyncMock(side_effect=discord.NotFound(MagicMock(), "no ban"))
    guild.unban = AsyncMock()
    return guild


async def test_unban_removes_identity_ban(
    wired_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    await wired_bot.stores.links.insert_one(
        Link(discord_user_id="555555", prn="PES1202100001", linked_at=datetime.now(UTC)),
    )
    await wired_bot.stores.server_bans.insert_one(
        ServerBan(prn="PES1202100001", discord_user_id="555555", reason="spam", banned_at=datetime.now(UTC)),
    )
    # An identity ban outlives a link row; /unban must resolve it from server_bans.
    await wired_bot.stores.links.delete_one(discord_user_id="555555")

    cmd = ModCommands()
    cmd.client = wired_bot
    mod = member_factory(user_id=1, roles=[wired_bot.config.mod_role])
    target = member_factory(user_id=555555, roles=[])
    guild = _unban_guild(banned=True)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild

    await get_callback(cmd.unban)(cmd, interaction, target, "appeal")

    guild.unban.assert_awaited()
    assert await wired_bot.stores.server_bans.has_active("PES1202100001") is False


async def test_unban_idempotent_when_already_clear(
    wired_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    cmd = ModCommands()
    cmd.client = wired_bot
    mod = member_factory(user_id=1, roles=[wired_bot.config.mod_role])
    target = member_factory(user_id=666666, roles=[])
    guild = _unban_guild(banned=False)
    interaction = interaction_factory(user=mod)
    interaction.guild = guild

    await get_callback(cmd.unban)(cmd, interaction, target)

    guild.unban.assert_not_called()
    description = interaction.followup.send.await_args.kwargs["embed"].description
    assert "was not Discord-banned" in description


async def test_ban_unban_reban_lifecycle(
    wired_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    await wired_bot.stores.links.insert_one(
        Link(discord_user_id="777777", prn="PES1202100001", linked_at=datetime.now(UTC)),
    )
    cmd = ModCommands()
    cmd.client = wired_bot
    mod = member_factory(user_id=1, roles=[wired_bot.config.mod_role])
    target = member_factory(user_id=777777, roles=[])
    interaction = interaction_factory(user=mod)

    interaction.guild = _ban_guild(target)
    await get_callback(cmd.ban)(cmd, interaction, target, "spam")
    assert await wired_bot.stores.server_bans.has_active("PES1202100001") is True

    interaction.guild = _unban_guild(banned=True)
    await get_callback(cmd.unban)(cmd, interaction, target, "appeal")
    assert await wired_bot.stores.server_bans.has_active("PES1202100001") is False

    interaction.guild = _ban_guild(target)
    await get_callback(cmd.ban)(cmd, interaction, target, "again")
    assert await wired_bot.stores.server_bans.has_active("PES1202100001") is True


@respx.mock
async def test_cross_account_evasion_matrix(wired_bot: MagicMock, member_factory: MemberFactory) -> None:
    await wired_bot.stores.links.insert_one(
        Link(discord_user_id="111111", prn="PES1202100001", linked_at=datetime.now(UTC)),
    )
    await wired_bot.stores.server_bans.insert_one(
        ServerBan(prn="PES1202100001", discord_user_id="111111", reason="spam", banned_at=datetime.now(UTC)),
    )
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json={"status": True, "profile": PROFILE}))

    helpers = GeneralHelpers()
    helpers.client = wired_bot
    helpers.cached_data = None

    message_b, _ = await helpers.link_account(member_factory(user_id=222222), "PES1202100001", "x")
    assert message_b == LinkMessage.PRN_BANNED

    other = {**PROFILE, "prn": "PES1202100002"}
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json={"status": True, "profile": other}))
    message_c, _ = await helpers.link_account(
        member_factory(user_id=333333, roles=[wired_bot.config.just_joined_role]), "PES1202100002", "x"
    )
    assert message_c == LinkMessage.SUCCESS
