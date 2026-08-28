from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, patch

import httpx
import respx

from src.cogs.general.helpers import GeneralHelpers, LinkMessage
from src.data.mongo import Student
from src.utils.config import Config

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from tests.conftest import MemberFactory

AUTH_URL = Config.PESU_AUTH_URL
PROFILE = {
    "prn": "PES1202100001",
    "branch": "Computer Science and Engineering",
    "campus": "RR",
    "campusCode": 1,
}


def _helpers(wired_bot: MagicMock) -> GeneralHelpers:
    helpers = GeneralHelpers()
    helpers.client = wired_bot
    helpers.cached_data = None
    return helpers


@respx.mock
async def test_link_account_persists_student_and_link(wired_bot: MagicMock, member_factory: MemberFactory) -> None:
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json={"status": True, "profile": PROFILE}))
    member = member_factory(user_id=1001, roles=[wired_bot.config.just_joined_role])

    with patch("src.cogs.general.helpers.ug.send_dm_safely", AsyncMock(return_value=True)):
        message, followup = await _helpers(wired_bot).link_account(member, "PES1202100001", "secret")

    assert message == LinkMessage.SUCCESS
    assert followup is not None

    link = await wired_bot.stores.links.find_one(discord_user_id="1001")
    assert link is not None
    assert link.prn == "PES1202100001"
    assert link.linked_at is not None

    student = await wired_bot.stores.students.find_one(prn="PES1202100001")
    assert student is not None
    assert student.branch_short == "CSE"
    assert student.campus == "RR"
    assert student.year == "2021"


@respx.mock
async def test_link_account_rejects_taken_prn(wired_bot: MagicMock, member_factory: MemberFactory) -> None:
    respx.post(AUTH_URL).mock(return_value=httpx.Response(200, json={"status": True, "profile": PROFILE}))
    first = member_factory(user_id=1001, roles=[wired_bot.config.just_joined_role])
    second = member_factory(user_id=1002, roles=[wired_bot.config.just_joined_role])

    with patch("src.cogs.general.helpers.ug.send_dm_safely", AsyncMock(return_value=True)):
        first_message, _ = await _helpers(wired_bot).link_account(first, "PES1202100001", "secret")
        second_message, second_followup = await _helpers(wired_bot).link_account(second, "PES1202100001", "secret")

    assert first_message == LinkMessage.SUCCESS
    assert second_message == LinkMessage.PRN_TAKEN
    assert second_followup is None
    assert await wired_bot.stores.links.find_one(discord_user_id="1002") is None
    assert await wired_bot.stores.links.exists(prn="PES1202100001") is True


async def test_student_upsert_by_prn_updates_existing(wired_bot: MagicMock) -> None:
    original = Student(
        prn="PES1UG21CS001",
        year="2021",
        branch_long="Computer Science",
        branch_short="CSE",
        campus="RR",
    )
    await wired_bot.stores.students.upsert_by_prn(original)
    await wired_bot.stores.students.upsert_by_prn(
        Student(
            prn="PES1UG21CS001",
            year="2022",
            branch_long="Computer Science",
            branch_short="CSE",
            campus="EC",
        )
    )
    found = await wired_bot.stores.students.find_one(prn="PES1UG21CS001")
    assert found is not None
    assert found.campus == "EC"
    assert found.year == "2022"
    assert await wired_bot.stores.students.find_many(prn="PES1UG21CS001") == [found]
