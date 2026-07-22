from __future__ import annotations

from src.cogs.events.listeners import EventListeners


async def test_member_join_linked_roles_with_mongo(
    wired_bot,
    sample_link_doc,
    sample_student_doc,
    member_factory,
) -> None:
    await wired_bot.student_collection.insert_one(sample_student_doc)
    await wired_bot.link_collection.insert_one({**sample_link_doc, "userId": "1001"})

    listeners = EventListeners()
    listeners.client = wired_bot
    member = member_factory(user_id=1001)

    await listeners.on_member_join(member)

    member.add_roles.assert_awaited()
    roles = member.add_roles.await_args.args
    assert wired_bot.config.linked_role in roles
    # Link should remain when all three academic roles resolve
    remaining = await wired_bot.link_collection.find_one({"userId": "1001"})
    assert remaining is not None


async def test_member_join_incomplete_student_deletes_link(wired_bot, member_factory) -> None:
    await wired_bot.student_collection.insert_one({"prn": "PES1UG21CS999", "year": "2021"})
    await wired_bot.link_collection.insert_one(
        {
            "_id": "incomplete-link",
            "userId": "2002",
            "prn": "PES1UG21CS999",
            "linkedAt": "2024-01-01T00:00:00Z",
        }
    )

    listeners = EventListeners()
    listeners.client = wired_bot
    member = member_factory(user_id=2002)

    await listeners.on_member_join(member)

    member.add_roles.assert_awaited_with(wired_bot.config.just_joined_role)
    assert await wired_bot.link_collection.find_one({"userId": "2002"}) is None


async def test_member_remove_deletes_unlinked_record(wired_bot, member_factory) -> None:
    await wired_bot.link_collection.insert_one({"_id": "leave-1", "userId": "3003", "linkedAt": None})
    listeners = EventListeners()
    listeners.client = wired_bot
    member = member_factory(user_id=3003)

    await listeners.on_member_remove(member)
    assert await wired_bot.link_collection.find_one({"userId": "3003"}) is None
