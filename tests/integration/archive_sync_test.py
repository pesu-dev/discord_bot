from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

from src.data.mongo import AnonBan, AnonMute, Mute

if TYPE_CHECKING:
    from unittest.mock import MagicMock


async def test_sync_archives_copies_hot_docs(wired_bot: MagicMock) -> None:
    now = datetime.now(UTC)
    mute = await wired_bot.stores.mutes.insert_one(
        Mute(
            discord_user_id="10",
            discord_channel_id=2001,
            moderator_discord_user_id="1",
            mute_time=now,
            original_unmute_time=now + timedelta(hours=1),
            reason="hot",
        )
    )
    anon_mute = await wired_bot.stores.anon_mutes.insert_one(
        AnonMute(
            discord_user_id="11",
            moderator_discord_user_id="1",
            muted_at=now,
            original_unmute_time=now + timedelta(hours=1),
            reason="hot",
        )
    )
    ban = await wired_bot.stores.anon_bans.insert_one(AnonBan(discord_user_id="12", reason="hot", banned_at=now))

    counts = await wired_bot.stores.sync_archives()
    assert counts["archive.mutes"] == 1
    assert counts["archive.anon_mutes"] == 1
    assert counts["archive.anon_bans"] == 1

    assert wired_bot.stores.mutes.archive is not None
    archived_mute = await wired_bot.stores.mutes.archive.find_one(id=mute.inserted_id)
    archived_anon_mute = await wired_bot.stores.anon_mutes.archive.find_one(id=anon_mute.inserted_id)
    archived_ban = await wired_bot.stores.anon_bans.archive.find_one(id=ban.inserted_id)
    assert archived_mute is not None and archived_mute.reason == "hot"
    assert archived_anon_mute is not None and archived_anon_mute.reason == "hot"
    assert archived_ban is not None and archived_ban.reason == "hot"


async def test_sync_archives_replaces_existing_archive_docs(wired_bot: MagicMock) -> None:
    now = datetime.now(UTC)
    result = await wired_bot.stores.mutes.insert_one(
        Mute(
            discord_user_id="20",
            discord_channel_id=2001,
            moderator_discord_user_id="1",
            mute_time=now,
            original_unmute_time=now + timedelta(hours=1),
            reason="v1",
        )
    )
    await wired_bot.stores.sync_archives()
    await wired_bot.stores.mutes.update_one(id=result.inserted_id, set_fields={"reason": "v2"})
    counts = await wired_bot.stores.sync_archives()
    assert counts["archive.mutes"] == 1

    assert wired_bot.stores.mutes.archive is not None
    archived = await wired_bot.stores.mutes.archive.find_one(id=result.inserted_id)
    assert archived is not None
    assert archived.reason == "v2"


async def test_replace_upsert_into_batches_on_real_mongo(wired_bot: MagicMock) -> None:
    now = datetime.now(UTC)
    ids = []
    for i in range(3):
        result = await wired_bot.stores.mutes.insert_one(
            Mute(
                discord_user_id=str(30 + i),
                discord_channel_id=2001,
                moderator_discord_user_id="1",
                mute_time=now,
                original_unmute_time=now + timedelta(hours=1),
                reason=f"m{i}",
            )
        )
        ids.append(result.inserted_id)

    assert wired_bot.stores.mutes.archive is not None
    written = await wired_bot.stores.mutes.replace_upsert_into(wired_bot.stores.mutes.archive, batch_size=2)
    assert written == 3
    for mute_id in ids:
        assert await wired_bot.stores.mutes.archive.find_one(id=mute_id) is not None
