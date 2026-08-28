from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from src.cogs.anon import SlashAnon
from src.cogs.mod.anon import AnonModCommands
from src.cogs.mod.helpers import ModHelpers
from src.data.mongo import AnonMute
from tests.helpers import get_callback

if TYPE_CHECKING:
    from tests.conftest import InteractionFactory, MemberFactory


class _Helpers(ModHelpers):
    pass


def _slash_anon(wired_bot: MagicMock) -> SlashAnon:
    with patch.object(
        SlashAnon,
        "__init__",
        lambda self, client: setattr(self, "client", client) or setattr(self, "tasks", []),
    ):
        return SlashAnon(wired_bot)


async def test_anon_mute_insert_and_active_lookup(wired_bot: MagicMock) -> None:
    helpers = _Helpers()
    helpers.client = wired_bot
    unmute_at = await helpers._create_and_store_anon_mute("9001", "1", "spam", seconds=3600)

    assert await wired_bot.stores.anon_mutes.has_active("9001") is True
    mute = await wired_bot.stores.anon_mutes.find_active("9001")
    assert mute is not None
    assert mute.reason == "spam"
    assert mute.unmuted_at is None
    assert abs(mute.original_unmute_time - unmute_at) < timedelta(seconds=1)


async def test_anon_mute_loop_expires_with_real_mongo(wired_bot: MagicMock) -> None:
    now = datetime.now(UTC)
    inserted = await wired_bot.stores.anon_mutes.insert_one(
        AnonMute(
            discord_user_id="55",
            moderator_discord_user_id="1",
            muted_at=now - timedelta(hours=2),
            original_unmute_time=now - timedelta(seconds=5),
            reason="expired",
        )
    )
    live = await wired_bot.stores.anon_mutes.insert_one(
        AnonMute(
            discord_user_id="56",
            moderator_discord_user_id="1",
            muted_at=now,
            original_unmute_time=now + timedelta(hours=1),
            reason="still muted",
        )
    )

    cog = _slash_anon(wired_bot)
    user = MagicMock()
    wired_bot.fetch_user = AsyncMock(return_value=user)
    with patch("src.utils.general.send_dm_safely", AsyncMock(return_value=True)) as dm:
        await SlashAnon.check_anon_mutes_loop(cog)

    expired = await wired_bot.stores.anon_mutes.find_one(id=inserted.inserted_id)
    still_active = await wired_bot.stores.anon_mutes.find_one(id=live.inserted_id)
    assert expired is not None and expired.unmuted_at is not None
    assert still_active is not None and still_active.unmuted_at is None
    assert await wired_bot.stores.anon_mutes.has_active("55") is False
    assert await wired_bot.stores.anon_mutes.has_active("56") is True
    dm.assert_awaited()


async def test_anon_unmute_user_with_real_mongo(
    wired_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    helpers = _Helpers()
    helpers.client = wired_bot
    await helpers._create_and_store_anon_mute("9003", "1", "trolling", seconds=3600)

    cmd = AnonModCommands()
    cmd.client = wired_bot
    member = member_factory(user_id=9003)
    with patch("src.utils.general.send_dm_safely", AsyncMock(return_value=True)):
        await get_callback(cmd.unmute_anon)(cmd, interaction_factory(), member)

    assert await wired_bot.stores.anon_mutes.has_active("9003") is False
    mute = await wired_bot.stores.anon_mutes.find_one(discord_user_id="9003")
    assert mute is not None
    assert mute.unmuted_at is not None
