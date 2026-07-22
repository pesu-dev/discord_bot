from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from src.cogs.events.listeners import EventListeners

if TYPE_CHECKING:
    import pytest

    from tests.conftest import MemberFactory


async def test_on_member_join_unlinked_record_deleted(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    member = member_factory(user_id=7)
    link = {"_id": "l1", "userId": "7", "linkedAt": None}
    mock_bot.link_collection.find_one = AsyncMock(return_value=link)
    mock_bot.link_collection.delete_one = AsyncMock()
    await listeners.on_member_join(member)
    member.add_roles.assert_awaited_with(mock_bot.config.just_joined_role)
    mock_bot.link_collection.delete_one.assert_awaited_once_with({"_id": "l1"})


async def test_on_member_join_missing_student(
    mock_bot: MagicMock, sample_link_doc: dict, member_factory: MemberFactory
) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    member = member_factory(user_id=1001)
    mock_bot.link_collection.find_one = AsyncMock(return_value=sample_link_doc)
    mock_bot.student_collection.find_one = AsyncMock(return_value=None)
    mock_bot.link_collection.delete_one = AsyncMock()
    await listeners.on_member_join(member)
    mock_bot.link_collection.delete_one.assert_awaited()


async def test_on_member_remove_keeps_complete_link(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    member = member_factory(user_id=55)
    mock_bot.link_collection.find_one = AsyncMock(return_value={"_id": "x", "userId": "55", "linkedAt": "2024-01-01"})
    mock_bot.link_collection.delete_one = AsyncMock()
    await listeners.on_member_remove(member)
    mock_bot.link_collection.delete_one.assert_not_called()


async def test_on_message_ignores_bots(mock_bot: MagicMock) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    message = MagicMock(spec=discord.Message)
    message.author.bot = True
    await listeners.on_message(message)


async def test_on_message_ec_campus_reply(mock_bot: MagicMock, monkeypatch: pytest.MonkeyPatch) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    monkeypatch.setenv("APP_ENV", "prod")
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


async def test_on_message_delete_ignores_bot(mock_bot: MagicMock) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    message = MagicMock(spec=discord.Message)
    message.author.bot = True
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


async def test_on_message_edit_ignores_bot(mock_bot: MagicMock) -> None:
    listeners = EventListeners()
    listeners.client = mock_bot
    before = MagicMock(spec=discord.Message)
    before.author.bot = True
    await listeners.on_message_edit(before, MagicMock())
    mock_bot.config.mod_logs_channel.send.assert_not_called()
