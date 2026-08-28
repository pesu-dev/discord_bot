from __future__ import annotations

from typing import TYPE_CHECKING

import pytest
from pymongo.errors import DuplicateKeyError

from src.data.mongo import Link, Student

if TYPE_CHECKING:
    from unittest.mock import MagicMock


async def test_link_discord_user_id_is_unique(wired_bot: MagicMock) -> None:
    await wired_bot.stores.links.insert_one(Link(discord_user_id="1001", prn="PES1UG21CS001"))
    with pytest.raises(DuplicateKeyError):
        await wired_bot.stores.links.insert_one(Link(discord_user_id="1001", prn="PES1UG21CS002"))


async def test_link_prn_is_unique(wired_bot: MagicMock) -> None:
    await wired_bot.stores.links.insert_one(Link(discord_user_id="1001", prn="PES1UG21CS001"))
    with pytest.raises(DuplicateKeyError):
        await wired_bot.stores.links.insert_one(Link(discord_user_id="1002", prn="PES1UG21CS001"))


async def test_student_prn_is_unique(wired_bot: MagicMock) -> None:
    student = Student(
        prn="PES1UG21CS001",
        year="2021",
        branch_long="Computer Science",
        branch_short="CSE",
        campus="RR",
    )
    await wired_bot.stores.students.insert_one(student)
    with pytest.raises(DuplicateKeyError):
        await wired_bot.stores.students.insert_one(
            Student(
                prn="PES1UG21CS001",
                year="2022",
                branch_long="Computer Science",
                branch_short="CSE",
                campus="EC",
            )
        )
