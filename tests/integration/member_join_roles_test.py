from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

from bson import ObjectId

from src.cogs.events.listeners import EventListeners
from src.data.mongo import Link, Student

if TYPE_CHECKING:
    from unittest.mock import MagicMock

    from tests.conftest import MemberFactory


async def test_member_join_linked_roles_with_mongo(
    wired_bot: MagicMock,
    sample_student_doc: dict,
    member_factory: MemberFactory,
) -> None:
    student = Student.from_document(sample_student_doc)
    await wired_bot.stores.students.insert_one(student)
    await wired_bot.stores.links.insert_one(
        Link(
            discord_user_id="1001",
            prn=student.prn,
            linked_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
    )

    listeners = EventListeners()
    listeners.client = wired_bot
    member = member_factory(user_id=1001)

    await listeners.on_member_join(member)

    member.add_roles.assert_awaited()
    roles = member.add_roles.await_args.args
    assert wired_bot.config.linked_role in roles
    remaining = await wired_bot.stores.links.find_one(discord_user_id="1001")
    assert remaining is not None


async def test_member_join_incomplete_student_deletes_link(wired_bot: MagicMock, member_factory: MemberFactory) -> None:
    await wired_bot.stores.students.insert_one(
        Student(
            prn="PES1UG21CS999",
            year="2021",
            branch_long="Computer Science",
            branch_short="",
            campus="RR",
        )
    )
    link = Link(
        id=ObjectId(),
        discord_user_id="2002",
        prn="PES1UG21CS999",
        linked_at=datetime(2024, 1, 1, tzinfo=UTC),
    )
    await wired_bot.stores.links.insert_one(link)

    listeners = EventListeners()
    listeners.client = wired_bot
    member = member_factory(user_id=2002)

    await listeners.on_member_join(member)

    member.add_roles.assert_awaited_with(wired_bot.config.just_joined_role)
    assert await wired_bot.stores.links.find_one(discord_user_id="2002") is None


async def test_member_remove_deletes_unlinked_record(wired_bot: MagicMock, member_factory: MemberFactory) -> None:
    await wired_bot.stores.links.insert_one(
        Link(id=ObjectId(), discord_user_id="3003", prn="PES1UG21CS001", linked_at=None)
    )
    listeners = EventListeners()
    listeners.client = wired_bot
    member = member_factory(user_id=3003)

    await listeners.on_member_remove(member)
    assert await wired_bot.stores.links.find_one(discord_user_id="3003") is None
