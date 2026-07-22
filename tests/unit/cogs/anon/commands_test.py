from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from src.cogs.anon import SlashAnon
from src.cogs.anon.commands import AnonCommands
from tests.helpers import get_callback

if TYPE_CHECKING:
    from tests.conftest import InteractionFactory, MemberFactory


class _AsyncIter:
    def __init__(self, items: list) -> None:
        self._items = items

    def __aiter__(self) -> _AsyncIter:
        self._iter = iter(self._items)
        return self

    async def __anext__(self) -> object:
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc


async def test_anon_send_locked_channel(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonCommands()
    cmd.client = mock_bot
    mock_bot.link_collection.find_one = AsyncMock(return_value={"userId": "1"})
    mock_bot.anonban_collection.find_one = AsyncMock(return_value=None)
    mock_bot.config.lobby_channel.permissions_for = MagicMock(return_value=MagicMock(send_messages=False))
    interaction = interaction_factory(user=member_factory())
    await get_callback(cmd.anon_send)(cmd, interaction, "hello")
    assert "locked" in interaction.followup.send.await_args.kwargs["content"].lower()


async def test_anon_send_reply_link(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonCommands()
    cmd.client = mock_bot
    mock_bot.link_collection.find_one = AsyncMock(return_value={"userId": "1001"})
    mock_bot.anonban_collection.find_one = AsyncMock(return_value=None)
    mock_bot.config.lobby_channel.permissions_for = MagicMock(return_value=MagicMock(send_messages=True))
    reply_msg = MagicMock()
    sent = MagicMock()
    sent.id = 777
    reply_msg.reply = AsyncMock(return_value=sent)
    mock_bot.config.lobby_channel.fetch_message = AsyncMock(return_value=reply_msg)
    interaction = interaction_factory(user=member_factory(user_id=1001))
    await get_callback(cmd.anon_send)(cmd, interaction, "hi", link="https://discord.com/channels/1/2/9")
    reply_msg.reply.assert_awaited()
    assert mock_bot.anon_cache["1001"][0]["message_id"] == "777"


async def test_anon_send_bad_reply_link(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonCommands()
    cmd.client = mock_bot
    mock_bot.link_collection.find_one = AsyncMock(return_value={"userId": "1001"})
    mock_bot.anonban_collection.find_one = AsyncMock(return_value=None)
    mock_bot.config.lobby_channel.permissions_for = MagicMock(return_value=MagicMock(send_messages=True))
    mock_bot.config.lobby_channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "x"))
    sent = MagicMock(id=1)
    mock_bot.config.lobby_channel.send = AsyncMock(return_value=sent)
    interaction = interaction_factory(user=member_factory(user_id=1001))
    await get_callback(cmd.anon_send)(cmd, interaction, "hi", link="https://discord.com/channels/1/2/9")
    mock_bot.config.lobby_channel.send.assert_awaited()


async def test_anon_ban_loop_expires(mock_bot: MagicMock) -> None:
    with patch.object(
        SlashAnon,
        "__init__",
        lambda self, client: setattr(self, "client", client) or setattr(self, "tasks", []),
    ):
        cog = SlashAnon(mock_bot)

    ban = {"_id": "b1", "userId": 55}
    mock_bot.anonban_collection.find = MagicMock(return_value=_AsyncIter([ban]))
    mock_bot.anonban_collection.update_one = AsyncMock()
    user = MagicMock()
    mock_bot.fetch_user = AsyncMock(return_value=user)
    with patch("src.utils.general.send_dm_safely", AsyncMock(return_value=True)) as dm:
        await SlashAnon.check_anon_bans_loop(cog)
    mock_bot.anonban_collection.update_one.assert_awaited()
    dm.assert_awaited()


async def test_anon_before_loops(mock_bot: MagicMock) -> None:
    with patch.object(
        SlashAnon,
        "__init__",
        lambda self, client: setattr(self, "client", client) or setattr(self, "tasks", []),
    ):
        cog = SlashAnon(mock_bot)
    mock_bot.wait_until_ready = AsyncMock()
    await SlashAnon.before_check_anon_bans_loop(cog)
    await SlashAnon.before_clear_anon_cache_loop(cog)
    assert mock_bot.wait_until_ready.await_count == 2


async def test_slash_anon_lifecycle(mock_bot: MagicMock) -> None:
    mock_bot.wait_until_ready = AsyncMock()
    with (
        patch("discord.ext.tasks.Loop.start"),
        patch("discord.ext.tasks.Loop.is_running", return_value=False),
        patch("discord.ext.tasks.Loop.cancel"),
    ):
        cog = SlashAnon(mock_bot)
        assert len(cog.tasks) == 2
        await cog.on_ready()
        await cog.cog_unload()
