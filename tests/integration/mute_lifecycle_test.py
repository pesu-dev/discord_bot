from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from src.cogs.mod import SlashMod
from src.data.mongo import Mute

if TYPE_CHECKING:
    from tests.conftest import MemberFactory


async def test_mute_document_round_trip(wired_bot: MagicMock) -> None:
    now = datetime.now(UTC)
    mute = Mute(
        discord_user_id="12345",
        discord_channel_id=2001,
        moderator_discord_user_id="1",
        mute_time=now,
        original_unmute_time=now + timedelta(hours=1),
        reason="test",
    )
    result = await wired_bot.stores.mutes.insert_one(mute)
    found = await wired_bot.stores.mutes.find_one(id=result.inserted_id)
    assert found is not None
    assert found.unmuted_at is None
    assert found.discord_user_id == "12345"

    await wired_bot.stores.mutes.unmute_user("12345", unmuted_at=now)
    updated = await wired_bot.stores.mutes.find_one(id=result.inserted_id)
    assert updated is not None
    assert updated.unmuted_at is not None


async def test_mute_loop_expires_with_real_mongo(wired_bot: MagicMock, member_factory: MemberFactory) -> None:
    now = datetime.now(UTC)
    mute = Mute(
        discord_user_id="50",
        discord_channel_id=2001,
        moderator_discord_user_id="1",
        mute_time=now - timedelta(hours=2),
        original_unmute_time=now - timedelta(seconds=5),
        reason="expired",
    )
    inserted = await wired_bot.stores.mutes.insert_one(mute)

    with patch.object(
        SlashMod,
        "__init__",
        lambda self, client: setattr(self, "client", client) or setattr(self, "tasks", []),
    ):
        cog = SlashMod(wired_bot)

    member = member_factory(user_id=50, roles=[wired_bot.config.muted_role])
    channel = MagicMock(spec=discord.TextChannel)
    channel.send = AsyncMock()
    wired_bot.config.guild = MagicMock()
    wired_bot.config.guild.fetch_member = AsyncMock(return_value=member)
    wired_bot.config.guild.get_channel = MagicMock(return_value=channel)
    wired_bot.config.mod_logs_channel.send = AsyncMock()

    await SlashMod.check_mutes_loop(cog)

    doc = await wired_bot.stores.mutes.find_one(id=inserted.inserted_id)
    assert doc is not None
    assert doc.unmuted_at is not None
    member.remove_roles.assert_awaited()
