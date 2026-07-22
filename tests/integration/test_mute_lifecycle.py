from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from src.cogs.mod import SlashMod
from src.cogs.mod.helpers import ModHelpers

if TYPE_CHECKING:
    from tests.conftest import MemberFactory


class _Helpers(ModHelpers):
    pass


async def test_mute_document_round_trip(wired_bot: MagicMock) -> None:
    now = datetime.now(UTC)
    record = {
        "user_id": 12345,
        "channel_id": 2001,
        "moderator_id": 1,
        "mute_time": now,
        "unmute_time": now + timedelta(hours=1),
        "reason": "test",
        "active": True,
        "is_self_mute": False,
    }
    result = await wired_bot.mute_collection.insert_one(record)
    found = await wired_bot.mute_collection.find_one({"_id": result.inserted_id})
    assert found is not None
    assert found["active"] is True
    assert found["user_id"] == 12345

    await wired_bot.mute_collection.update_many(
        {"user_id": 12345, "active": True},
        {"$set": {"active": False, "unmute_type": "manual"}},
    )
    updated = await wired_bot.mute_collection.find_one({"_id": result.inserted_id})
    assert updated["active"] is False
    assert updated["unmute_type"] == "manual"


async def test_mute_loop_expires_with_real_mongo(wired_bot: MagicMock, member_factory: MemberFactory) -> None:
    now = datetime.now(UTC)
    inserted = await wired_bot.mute_collection.insert_one(
        {
            "user_id": 50,
            "channel_id": 2001,
            "moderator_id": 1,
            "mute_time": now - timedelta(hours=2),
            "unmute_time": now - timedelta(seconds=5),
            "reason": "expired",
            "active": True,
            "is_self_mute": False,
        }
    )

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

    doc = await wired_bot.mute_collection.find_one({"_id": inserted.inserted_id})
    assert doc["active"] is False
    assert doc["unmute_type"] == "loop_auto"
    member.remove_roles.assert_awaited()
