from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import discord
from bson import ObjectId

from src.cogs.events.helpers import EventHelpers
from src.cogs.events.listeners import EventListeners
from src.data.mongo import Branch, Campus, Link, Student

if TYPE_CHECKING:
    from tests.conftest import MemberFactory


def test_filter_reply_mentions_strips_replied_author() -> None:
    replied = MagicMock(spec=discord.Member)
    replied.id = 11
    other = MagicMock(spec=discord.Member)
    other.id = 22

    resolved = MagicMock(spec=discord.Message)
    resolved.author = replied

    message = MagicMock(spec=discord.Message)
    message.type = discord.MessageType.reply
    message.reference = MagicMock()
    message.reference.resolved = resolved
    message.mentions = [replied, other]

    filtered = EventHelpers._filter_reply_mentions(message)
    assert [m.id for m in filtered] == [22]


def test_filter_reply_mentions_reply_author_not_in_mentions() -> None:
    replied = MagicMock(spec=discord.Member)
    replied.id = 11
    other = MagicMock(spec=discord.Member)
    other.id = 22

    resolved = MagicMock(spec=discord.Message)
    resolved.author = replied

    message = MagicMock(spec=discord.Message)
    message.type = discord.MessageType.reply
    message.reference = MagicMock()
    message.reference.resolved = resolved
    message.mentions = [other]

    filtered = EventHelpers._filter_reply_mentions(message)
    assert [m.id for m in filtered] == [22]


def test_filter_reply_mentions_non_reply() -> None:
    user = MagicMock(spec=discord.Member)
    user.id = 1
    message = MagicMock(spec=discord.Message)
    message.type = discord.MessageType.default
    message.mentions = [user]
    assert EventHelpers._filter_reply_mentions(message) == [user]


def test_ghost_ping_field_helpers() -> None:
    embed = discord.Embed(title="t")
    author = MagicMock()
    author.mention = "<@1>"
    channel = MagicMock()
    channel.mention = "<#2>"
    message = MagicMock(spec=discord.Message)
    message.mention_everyone = True
    message.author = author
    message.channel = channel

    EventHelpers._add_everyone_ping_field(embed, message)
    assert len(embed.fields) == 1

    role = MagicMock()
    role.mention = "<@&3>"
    EventHelpers._add_role_ping_fields(embed, [role], message)
    assert any(f.name == "Role pings" for f in embed.fields)

    human = MagicMock(spec=discord.Member)
    human.bot = False
    human.mention = "<@4>"
    bot = MagicMock(spec=discord.Member)
    bot.bot = True
    EventHelpers._add_member_ping_fields(embed, [human, bot], message)
    assert any(f.name == "Member pings" for f in embed.fields)


def test_add_member_ping_fields_skips_bots_only() -> None:
    embed = discord.Embed(title="t")
    author = MagicMock()
    author.mention = "<@1>"
    channel = MagicMock()
    channel.mention = "<#2>"
    message = MagicMock(spec=discord.Message)
    message.author = author
    message.channel = channel
    bot = MagicMock(spec=discord.Member)
    bot.bot = True
    EventHelpers._add_member_ping_fields(embed, [bot], message)
    assert embed.fields == []


async def test_on_member_join_assigns_linked_roles(
    mock_bot: MagicMock,
    sample_link: Link,
    sample_student: Student,
    member_factory: MemberFactory,
) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    member = member_factory(user_id=1001)

    mock_bot.stores.links.find_one = AsyncMock(return_value=sample_link)
    mock_bot.stores.students.find_one = AsyncMock(return_value=sample_student)

    await listeners.on_member_join(member)

    mock_bot.config.bot_logs_channel.send.assert_awaited()
    member.add_roles.assert_awaited()
    roles = member.add_roles.await_args.args
    assert mock_bot.config.linked_role in roles
    mock_bot.stores.links.delete_one.assert_not_called()


async def test_on_member_join_incomplete_student_deletes_link(
    mock_bot: MagicMock,
    sample_link: Link,
    member_factory: MemberFactory,
) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    member = member_factory(user_id=1001)

    # Empty branch short skips that role → fewer than 3 academic roles → delete link
    incomplete = Student(
        prn="PES1UG21CS001",
        year="2021",
        branch=Branch(full="Computer Science", short=""),
        campus=Campus(code=1, short="RR"),
    )
    mock_bot.stores.links.find_one = AsyncMock(return_value=sample_link)
    mock_bot.stores.students.find_one = AsyncMock(return_value=incomplete)
    mock_bot.stores.links.delete_one = AsyncMock()

    await listeners.on_member_join(member)

    member.add_roles.assert_awaited_with(mock_bot.config.just_joined_role)
    mock_bot.stores.links.delete_one.assert_awaited_once_with(id=sample_link.id)


async def test_on_member_join_no_link(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    member = member_factory()
    mock_bot.stores.links.find_one = AsyncMock(return_value=None)

    await listeners.on_member_join(member)
    member.add_roles.assert_awaited_with(mock_bot.config.just_joined_role)


async def test_on_member_remove_deletes_incomplete_link(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    member = member_factory(user_id=55)
    link = Link(id=ObjectId(), user_id="55", prn="PES1UG21CS001", linked_at=None)
    mock_bot.stores.links.find_one = AsyncMock(return_value=link)
    mock_bot.stores.links.delete_one = AsyncMock()

    await listeners.on_member_remove(member)
    mock_bot.stores.links.delete_one.assert_awaited_once_with(id=link.id)


async def test_on_message_delete_sends_ghost_ping(mock_bot: MagicMock) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    author = MagicMock()
    author.bot = False
    author.mention = "<@9>"
    channel = MagicMock()
    channel.mention = "<#1>"
    target = MagicMock(spec=discord.Member)
    target.bot = False
    target.mention = "<@8>"

    message = MagicMock(spec=discord.Message)
    message.author = author
    message.channel = channel
    message.mention_everyone = False
    message.role_mentions = []
    message.mentions = [target]
    message.content = "hi <@8>"

    await listeners.on_message_delete(message)
    mock_bot.config.mod_logs_channel.send.assert_awaited()


async def test_on_thread_create_joins(mock_bot: MagicMock) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    thread = MagicMock(spec=discord.Thread)
    thread.join = AsyncMock()
    await listeners.on_thread_create(thread)
    thread.join.assert_awaited_once()


def test_filter_reply_exception_path() -> None:
    resolved = MagicMock(spec=discord.Message)
    type(resolved).author = property(lambda self: (_ for _ in ()).throw(RuntimeError("boom")))
    message = MagicMock(spec=discord.Message)
    message.type = discord.MessageType.reply
    message.reference = MagicMock()
    message.reference.resolved = resolved
    message.mentions = [MagicMock()]
    assert EventHelpers._filter_reply_mentions(message) == message.mentions


def test_filter_reply_non_message_resolved() -> None:
    message = MagicMock(spec=discord.Message)
    message.type = discord.MessageType.reply
    message.reference = MagicMock()
    message.reference.resolved = MagicMock()
    user = MagicMock()
    message.mentions = [user]
    assert EventHelpers._filter_reply_mentions(message) == [user]
