from __future__ import annotations

from datetime import UTC, datetime, timedelta
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

    expiry = await helpers._create_and_store_ban("9001", "spam", "1h")
    assert expiry != "Permanent"

    assert await helpers._check_user_anon_ban("9001") is True

    # Expire it the way the anon loop would
    ban = await wired_bot.stores.anonbans.find_one(user_id="9001", active=True)
    assert ban is not None and ban.id is not None
    await wired_bot.stores.anonbans.update_one(id=ban.id, set_fields={"active": False})
    assert await helpers._check_user_anon_ban("9001") is False


async def test_anonban_permanent(wired_bot: MagicMock) -> None:
    helpers = _Helpers()
    helpers.client = wired_bot
    assert await helpers._create_and_store_ban("9002", "perm") == "Permanent"
    ban = await wired_bot.stores.anonbans.find_one(user_id="9002")
    assert ban is not None
    assert ban.expires_at is None
    assert ban.active is True


async def test_apply_anon_ban_persists(
    wired_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    helpers = _Helpers()
    helpers.client = wired_bot
    member = member_factory(user_id=9003)
    interaction = interaction_factory()

    with patch("src.utils.general.send_dm_safely", AsyncMock(return_value=True)):
        await helpers._apply_anon_ban(interaction, member, time="2h", reason="trolling")

    ban = await wired_bot.stores.anonbans.find_one(user_id="9003", active=True)
    assert isinstance(ban, AnonBan)
    assert ban.reason == "trolling"
    assert isinstance(ban.banned_at, datetime)
    assert ban.expires_at is not None
    assert ban.expires_at > datetime.now(UTC) - timedelta(seconds=1)
