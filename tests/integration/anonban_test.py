from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from src.cogs.mod.helpers import ModHelpers
from src.data.mongo import AnonBan

if TYPE_CHECKING:
    from tests.conftest import InteractionFactory, MemberFactory


class _Helpers(ModHelpers):
    pass


async def test_anonban_insert_and_lookup(wired_bot: MagicMock) -> None:
    helpers = _Helpers()
    helpers.client = wired_bot

    await helpers._create_and_store_ban("9001", "spam")
    assert await wired_bot.stores.anon_bans.has_active("9001") is True

    ban = await wired_bot.stores.anon_bans.find_active("9001")
    assert ban is not None and ban.id is not None
    await wired_bot.stores.anon_bans.unban("9001", unbanned_at=datetime.now(UTC))
    assert await wired_bot.stores.anon_bans.has_active("9001") is False


async def test_anonban_permanent(wired_bot: MagicMock) -> None:
    helpers = _Helpers()
    helpers.client = wired_bot
    await helpers._create_and_store_ban("9002", "perm")
    ban = await wired_bot.stores.anon_bans.find_one(discord_user_id="9002")
    assert ban is not None
    assert ban.unbanned_at is None


async def test_apply_anon_ban_persists(
    wired_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    helpers = _Helpers()
    helpers.client = wired_bot
    member = member_factory(user_id=9003)
    interaction = interaction_factory()

    with patch("src.utils.general.send_dm_safely", AsyncMock(return_value=True)):
        await helpers._apply_anon_ban(interaction, member, reason="trolling")

    ban = await wired_bot.stores.anon_bans.find_active("9003")
    assert isinstance(ban, AnonBan)
    assert ban.reason == "trolling"
    assert isinstance(ban.banned_at, datetime)
    assert ban.unbanned_at is None
