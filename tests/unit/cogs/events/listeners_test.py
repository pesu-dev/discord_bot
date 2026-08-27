from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from bson import ObjectId

from src.cogs.events.listeners import EventListeners
from src.data.mongo import Link, Student

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from tests.conftest import MemberFactory


def _make_listeners(mock_bot: MagicMock) -> EventListeners:
    listeners = EventListeners()
    listeners.client = mock_bot
    listeners._fafo_lock = asyncio.Lock()
    listeners._fafo_message_id = None
    mock_bot.user = MagicMock()
    mock_bot.user.id = 42
    return listeners


async def _empty_pins(*, limit: int | None = None) -> AsyncIterator[None]:
    return
    yield


def _honeypot_message(mock_bot: MagicMock, author: MagicMock, *, content: str = "spam") -> MagicMock:
    message = MagicMock(spec=discord.Message)
    message.author = author
    message.author.bot = False
    message.channel = mock_bot.config.honeypot_channel
    message.content = content
    message.delete = AsyncMock()
    return message


async def test_on_member_join_unlinked_record_deleted(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    member = member_factory(user_id=7)
    link = Link(id=ObjectId(), discord_user_id="7", prn="PES1UG21CS001", linked_at=None)
    mock_bot.stores.links.find_one = AsyncMock(return_value=link)
    mock_bot.stores.links.delete_one = AsyncMock()
    await listeners.on_member_join(member)
    member.add_roles.assert_awaited_with(mock_bot.config.just_joined_role)
    mock_bot.stores.links.delete_one.assert_awaited_once_with(id=link.id)


async def test_on_member_join_skips_non_prod(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    mock_bot.config.env = "dev"
    mock_bot.stores.links.find_one = AsyncMock()
    await listeners.on_member_join(member_factory(user_id=7))
    mock_bot.stores.links.find_one.assert_not_called()
    mock_bot.config.bot_logs_channel.send.assert_not_called()


async def test_on_member_join_missing_student(
    mock_bot: MagicMock, sample_link: Link, member_factory: MemberFactory
) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    member = member_factory(user_id=1001)
    mock_bot.stores.links.find_one = AsyncMock(return_value=sample_link)
    mock_bot.stores.students.find_one = AsyncMock(return_value=None)
    mock_bot.stores.links.delete_one = AsyncMock()
    await listeners.on_member_join(member)
    mock_bot.stores.links.delete_one.assert_awaited()


async def test_on_member_join_academic_role_value_error(
    mock_bot: MagicMock, sample_link: Link, sample_student: Student, member_factory: MemberFactory
) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    member = member_factory(user_id=1001)
    mock_bot.stores.links.find_one = AsyncMock(return_value=sample_link)
    mock_bot.stores.students.find_one = AsyncMock(return_value=sample_student)
    mock_bot.stores.links.delete_one = AsyncMock()
    mock_bot.config.resolve_academic_role = MagicMock(side_effect=ValueError("unknown"))
    await listeners.on_member_join(member)
    member.add_roles.assert_awaited_with(mock_bot.config.just_joined_role)
    mock_bot.stores.links.delete_one.assert_awaited()


async def test_on_member_remove_keeps_complete_link(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    member = member_factory(user_id=55)
    mock_bot.stores.links.find_one = AsyncMock(
        return_value=Link(
            id=ObjectId(),
            discord_user_id="55",
            prn="PES1UG21CS001",
            linked_at=datetime(2024, 1, 1, tzinfo=UTC),
        )
    )
    mock_bot.stores.links.delete_one = AsyncMock()
    await listeners.on_member_remove(member)
    mock_bot.stores.links.delete_one.assert_not_called()


async def test_on_member_remove_skips_non_prod(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    mock_bot.config.env = "local"
    mock_bot.stores.links.find_one = AsyncMock()
    await listeners.on_member_remove(member_factory(user_id=55))
    mock_bot.stores.links.find_one.assert_not_called()
    mock_bot.config.bot_logs_channel.send.assert_not_called()


async def test_on_message_ignores_bots(mock_bot: MagicMock) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    message = MagicMock(spec=discord.Message)
    message.author.bot = True
    await listeners.on_message(message)


async def test_on_message_ec_campus_reply(mock_bot: MagicMock) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    message = MagicMock(spec=discord.Message)
    message.author.bot = False
    message.content = "anyone at EC campus?"
    message.reply = AsyncMock()
    message.channel.typing = MagicMock(return_value=AsyncMock())
    message.channel.typing.return_value.__aenter__ = AsyncMock(return_value=None)
    message.channel.typing.return_value.__aexit__ = AsyncMock(return_value=None)
    message.channel.send = AsyncMock()
    with (
        patch("src.cogs.events.listeners.random.random", return_value=0.1),
        patch("src.cogs.events.listeners.asyncio.sleep", AsyncMock()),
    ):
        await listeners.on_message(message)
    message.reply.assert_awaited()
    message.channel.send.assert_awaited()


async def test_on_message_skips_non_prod(mock_bot: MagicMock) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    mock_bot.config.env = "local"
    message = MagicMock(spec=discord.Message)
    message.author.bot = False
    message.content = "ec campus"
    message.reply = AsyncMock()
    await listeners.on_message(message)
    message.reply.assert_not_called()


async def test_on_message_skips_when_random_misses(mock_bot: MagicMock) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    message = MagicMock(spec=discord.Message)
    message.author.bot = False
    message.content = "ec campus"
    message.reply = AsyncMock()
    with patch("src.cogs.events.listeners.random.random", return_value=0.9):
        await listeners.on_message(message)
    message.reply.assert_not_called()


async def test_on_message_skips_without_ec_pattern(mock_bot: MagicMock) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    message = MagicMock(spec=discord.Message)
    message.author.bot = False
    message.content = "hello world"
    message.reply = AsyncMock()
    with patch("src.cogs.events.listeners.random.random", return_value=0.1):
        await listeners.on_message(message)
    message.reply.assert_not_called()


async def test_on_message_delete_ignores_bot(mock_bot: MagicMock) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    message = MagicMock(spec=discord.Message)
    message.author.bot = True
    await listeners.on_message_delete(message)
    mock_bot.config.mod_logs_channel.send.assert_not_called()


async def test_on_message_delete_no_pings(mock_bot: MagicMock) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    message = MagicMock(spec=discord.Message)
    message.author.bot = False
    message.mention_everyone = False
    message.role_mentions = []
    message.mentions = []
    message.content = "hi"
    await listeners.on_message_delete(message)
    mock_bot.config.mod_logs_channel.send.assert_not_called()


async def test_on_message_edit_ghost_ping(mock_bot: MagicMock) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot

    author = MagicMock()
    author.bot = False
    author.mention = "<@1>"
    channel = MagicMock()
    channel.mention = "<#2>"

    mentioned = MagicMock(spec=discord.Member)
    mentioned.id = 99
    mentioned.bot = False
    mentioned.mention = "<@99>"

    before = MagicMock(spec=discord.Message)
    before.author = author
    before.channel = channel
    before.type = discord.MessageType.default
    before.mentions = [mentioned]
    before.role_mentions = []
    before.mention_everyone = False
    before.jump_url = "https://discord.com/channels/1/2/3"

    after = MagicMock(spec=discord.Message)
    after.author = author
    after.mentions = []
    after.role_mentions = []
    after.mention_everyone = False

    await listeners.on_message_edit(before, after)
    mock_bot.config.mod_logs_channel.send.assert_awaited()


async def test_on_message_edit_no_mention_change(mock_bot: MagicMock) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    author = MagicMock()
    author.bot = False
    before = MagicMock(spec=discord.Message)
    before.author = author
    before.type = discord.MessageType.default
    before.mentions = []
    before.role_mentions = []
    before.mention_everyone = False
    after = MagicMock(spec=discord.Message)
    after.mentions = []
    after.role_mentions = []
    after.mention_everyone = False
    await listeners.on_message_edit(before, after)
    mock_bot.config.mod_logs_channel.send.assert_not_called()


async def test_on_message_edit_mention_change_bots_only(mock_bot: MagicMock) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    author = MagicMock()
    author.bot = False
    bot_user = MagicMock(spec=discord.Member)
    bot_user.id = 7
    bot_user.bot = True
    before = MagicMock(spec=discord.Message)
    before.author = author
    before.type = discord.MessageType.default
    before.mentions = [bot_user]
    before.role_mentions = []
    before.mention_everyone = False
    before.jump_url = "https://discord.com/channels/1/2/3"
    after = MagicMock(spec=discord.Message)
    after.mentions = []
    after.role_mentions = []
    after.mention_everyone = False
    await listeners.on_message_edit(before, after)
    mock_bot.config.mod_logs_channel.send.assert_not_called()


async def test_on_message_edit_ignores_bot(mock_bot: MagicMock) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    before = MagicMock(spec=discord.Message)
    before.author.bot = True
    await listeners.on_message_edit(before, MagicMock())
    mock_bot.config.mod_logs_channel.send.assert_not_called()


async def test_on_message_honeypot_skips_non_member(mock_bot: MagicMock) -> None:
    listeners = _make_listeners(mock_bot)
    author = MagicMock(spec=discord.User)
    author.bot = False
    message = _honeypot_message(mock_bot, author)
    message.reply = AsyncMock()
    with patch("src.cogs.events.listeners.random.random", return_value=0.9):
        await listeners.on_message(message)
    message.delete.assert_not_called()
    mock_bot.config.mod_logs_channel.send.assert_not_called()


async def test_on_message_honeypot_skips_protected_user(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    listeners = _make_listeners(mock_bot)
    author = member_factory(user_id=1001, roles=[mock_bot.config.admin_role])
    message = _honeypot_message(mock_bot, author)
    message.delete = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no"))

    await listeners.on_message(message)

    sent = mock_bot.config.mod_logs_channel.send.await_args.args[0]
    assert "protected user" in sent


async def test_on_message_honeypot_kick_success(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    listeners = _make_listeners(mock_bot)
    author = member_factory(user_id=1001)
    author.guild = MagicMock()
    author.guild.name = "PESU"
    author.roles = []
    message = _honeypot_message(mock_bot, author, content="")
    message.delete = AsyncMock(side_effect=discord.NotFound(MagicMock(), "gone"))

    banner = MagicMock(spec=discord.Message)
    banner.id = 11
    banner.pin = AsyncMock()
    banner.edit = AsyncMock()
    banner.components = []
    mock_bot.config.honeypot_channel.pins = _empty_pins
    mock_bot.config.honeypot_channel.send = AsyncMock(return_value=banner)

    with patch("src.cogs.events.helpers.ug.send_dm_safely", AsyncMock(return_value=True)):
        await listeners.on_message(message)

    author.timeout.assert_awaited()
    author.kick.assert_awaited()
    banner.edit.assert_awaited()
    embed = mock_bot.config.mod_logs_channel.send.await_args.kwargs["embed"]
    assert embed.title == "Honeypot Triggered"
    assert any(field.value == "*No content*" for field in embed.fields)


async def test_on_message_honeypot_forbidden(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    listeners = _make_listeners(mock_bot)
    author = member_factory(user_id=1001)
    author.roles = []
    message = _honeypot_message(mock_bot, author)
    listeners._apply_honeypot_action = AsyncMock(side_effect=discord.Forbidden(MagicMock(), "no"))

    await listeners.on_message(message)

    sent = mock_bot.config.mod_logs_channel.send.await_args.args[0]
    assert "missing permissions" in sent


async def test_on_message_honeypot_http_exception(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    listeners = _make_listeners(mock_bot)
    author = member_factory(user_id=1001)
    author.roles = []
    message = _honeypot_message(mock_bot, author)
    listeners._apply_honeypot_action = AsyncMock(side_effect=discord.HTTPException(MagicMock(), "fail"))

    await listeners.on_message(message)

    sent = mock_bot.config.mod_logs_channel.send.await_args.args[0]
    assert "Failed honeypot action" in sent
