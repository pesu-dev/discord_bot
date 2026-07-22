from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

import discord

from src.cogs.events.helpers import EventHelpers
from src.cogs.events.listeners import EventListeners

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


async def test_on_member_join_assigns_linked_roles(
    mock_bot: MagicMock,
    sample_link_doc: dict,
    sample_student_doc: dict,
    member_factory: MemberFactory,
) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    member = member_factory(user_id=1001)

    mock_bot.link_collection.find_one = AsyncMock(return_value=sample_link_doc)
    mock_bot.student_collection.find_one = AsyncMock(return_value=sample_student_doc)

    await listeners.on_member_join(member)

    mock_bot.config.bot_logs_channel.send.assert_awaited()
    member.add_roles.assert_awaited()
    roles = member.add_roles.await_args.args
    assert mock_bot.config.linked_role in roles
    mock_bot.link_collection.delete_one.assert_not_called()


async def test_on_member_join_incomplete_student_deletes_link(
    mock_bot: MagicMock,
    sample_link_doc: dict,
    member_factory: MemberFactory,
) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    member = member_factory(user_id=1001)

    mock_bot.link_collection.find_one = AsyncMock(return_value=sample_link_doc)
    mock_bot.student_collection.find_one = AsyncMock(
        return_value={"prn": "PES1UG21CS001", "year": "2021"}  # missing branch/campus
    )
    mock_bot.link_collection.delete_one = AsyncMock()

    await listeners.on_member_join(member)

    member.add_roles.assert_awaited_with(mock_bot.config.just_joined_role)
    mock_bot.link_collection.delete_one.assert_awaited_once_with({"_id": sample_link_doc["_id"]})


async def test_on_member_join_no_link(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    member = member_factory()
    mock_bot.link_collection.find_one = AsyncMock(return_value=None)

    await listeners.on_member_join(member)
    member.add_roles.assert_awaited_with(mock_bot.config.just_joined_role)


async def test_on_member_remove_deletes_incomplete_link(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    member = member_factory(user_id=55)
    mock_bot.link_collection.find_one = AsyncMock(return_value={"_id": "x", "userId": "55", "linkedAt": None})
    mock_bot.link_collection.delete_one = AsyncMock()

    await listeners.on_member_remove(member)
    mock_bot.link_collection.delete_one.assert_awaited_once_with({"_id": "x"})


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
