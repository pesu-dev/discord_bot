from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

from src.cogs.mod import SlashMod
from src.data.mongo import AnonBan, AnonMute, Mute

if TYPE_CHECKING:
    from bson import ObjectId


def _slash_mod(wired_bot: MagicMock) -> SlashMod:
    with patch.object(
        SlashMod,
        "__init__",
        lambda self, client: setattr(self, "client", client) or setattr(self, "tasks", []),
    ):
        return SlashMod(wired_bot)


async def _insert_mute(wired_bot: MagicMock, *, user_id: str, unmuted_at: datetime | None) -> ObjectId:
    now = datetime.now(UTC)
    result = await wired_bot.stores.mutes.insert_one(
        Mute(
            discord_user_id=user_id,
            discord_channel_id=2001,
            moderator_discord_user_id="1",
            mute_time=now - timedelta(days=3),
            original_unmute_time=now - timedelta(days=2),
            reason="x",
            unmuted_at=unmuted_at,
        )
    )
    return result.inserted_id


async def _insert_anon_mute(wired_bot: MagicMock, *, user_id: str, unmuted_at: datetime | None) -> ObjectId:
    now = datetime.now(UTC)
    result = await wired_bot.stores.anon_mutes.insert_one(
        AnonMute(
            discord_user_id=user_id,
            moderator_discord_user_id="1",
            muted_at=now - timedelta(days=3),
            original_unmute_time=now - timedelta(days=2),
            reason="x",
            unmuted_at=unmuted_at,
        )
    )
    return result.inserted_id


async def _insert_anon_ban(wired_bot: MagicMock, *, user_id: str, unbanned_at: datetime | None) -> ObjectId:
    now = datetime.now(UTC)
    result = await wired_bot.stores.anon_bans.insert_one(
        AnonBan(
            discord_user_id=user_id,
            reason="x",
            banned_at=now - timedelta(days=3),
            unbanned_at=unbanned_at,
        )
    )
    return result.inserted_id


async def test_cleanup_stale_records_loop_with_real_mongo(wired_bot: MagicMock) -> None:
    now = datetime.now(UTC)
    old = now - timedelta(days=2)
    recent = now - timedelta(hours=1)

    stale_mute = await _insert_mute(wired_bot, user_id="1", unmuted_at=old)
    fresh_mute = await _insert_mute(wired_bot, user_id="2", unmuted_at=recent)
    active_mute = await _insert_mute(wired_bot, user_id="3", unmuted_at=None)

    stale_anon_mute = await _insert_anon_mute(wired_bot, user_id="4", unmuted_at=old)
    fresh_anon_mute = await _insert_anon_mute(wired_bot, user_id="5", unmuted_at=recent)
    active_anon_mute = await _insert_anon_mute(wired_bot, user_id="6", unmuted_at=None)

    stale_ban = await _insert_anon_ban(wired_bot, user_id="7", unbanned_at=old)
    fresh_ban = await _insert_anon_ban(wired_bot, user_id="8", unbanned_at=recent)
    active_ban = await _insert_anon_ban(wired_bot, user_id="9", unbanned_at=None)

    await SlashMod.cleanup_stale_records_loop(_slash_mod(wired_bot))

    assert await wired_bot.stores.mutes.find_one(id=stale_mute) is None
    assert await wired_bot.stores.mutes.find_one(id=fresh_mute) is not None
    assert await wired_bot.stores.mutes.find_one(id=active_mute) is not None

    assert await wired_bot.stores.anon_mutes.find_one(id=stale_anon_mute) is None
    assert await wired_bot.stores.anon_mutes.find_one(id=fresh_anon_mute) is not None
    assert await wired_bot.stores.anon_mutes.find_one(id=active_anon_mute) is not None

    assert await wired_bot.stores.anon_bans.find_one(id=stale_ban) is None
    assert await wired_bot.stores.anon_bans.find_one(id=fresh_ban) is not None
    assert await wired_bot.stores.anon_bans.find_one(id=active_ban) is not None
