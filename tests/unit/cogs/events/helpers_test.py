from __future__ import annotations

import asyncio
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import discord
from bson import ObjectId

from src.cogs.events.helpers import EventHelpers
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


def _pins(*messages: MagicMock) -> object:
    async def _iter(*, limit: int | None = None) -> AsyncIterator[MagicMock]:
        for message in messages:
            yield message

    return _iter


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
        branch_long="Computer Science",
        branch_short="",
        campus="RR",
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
    link = Link(id=ObjectId(), discord_user_id="55", prn="PES1UG21CS001", linked_at=None)
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


def test_build_fafo_banner_and_view() -> None:
    helpers = EventHelpers()
    embed = helpers._build_fafo_banner()
    assert embed.title == "DO NOT SEND MESSAGES IN THIS CHANNEL"
    view = EventHelpers._build_fafo_view(7)
    assert view.timeout is None
    button = view.children[0]
    assert isinstance(button, discord.ui.Button)
    assert button.label == "🍯 Timeouts & Kicks: 7"
    assert button.disabled is True


async def test_ensure_fafo_banner_fetches_cached_message(mock_bot: MagicMock) -> None:
    listeners = _make_listeners(mock_bot)
    listeners._fafo_message_id = 99
    cached = MagicMock(spec=discord.Message)
    mock_bot.config.honeypot_channel.fetch_message = AsyncMock(return_value=cached)
    mock_bot.config.honeypot_channel.pins = _pins()

    assert await listeners._ensure_fafo_banner() is cached
    mock_bot.config.honeypot_channel.fetch_message.assert_awaited_once_with(99)
    mock_bot.config.honeypot_channel.send.assert_not_called()


async def test_ensure_fafo_banner_recovers_from_missing_cache(mock_bot: MagicMock) -> None:
    listeners = _make_listeners(mock_bot)
    listeners._fafo_message_id = 99
    channel = mock_bot.config.honeypot_channel
    channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "x"))

    pinned = MagicMock(spec=discord.Message)
    pinned.id = 501
    pinned.author.id = mock_bot.user.id
    pinned.embeds = [MagicMock(title="DO NOT SEND MESSAGES IN THIS CHANNEL")]
    channel.pins = _pins(pinned)

    assert await listeners._ensure_fafo_banner() is pinned
    assert listeners._fafo_message_id == 501
    channel.send.assert_not_called()


async def test_ensure_fafo_banner_skips_non_matching_pins(mock_bot: MagicMock) -> None:
    listeners = _make_listeners(mock_bot)
    channel = mock_bot.config.honeypot_channel

    other_author = MagicMock(spec=discord.Message)
    other_author.author.id = 7
    other_author.embeds = [MagicMock(title="DO NOT SEND MESSAGES IN THIS CHANNEL")]

    no_embeds = MagicMock(spec=discord.Message)
    no_embeds.author.id = mock_bot.user.id
    no_embeds.embeds = []

    wrong_title = MagicMock(spec=discord.Message)
    wrong_title.author.id = mock_bot.user.id
    wrong_title.embeds = [MagicMock(title="something else")]

    channel.pins = _pins(other_author, no_embeds, wrong_title)
    created = MagicMock(spec=discord.Message)
    created.id = 808
    created.pin = AsyncMock()
    channel.send = AsyncMock(return_value=created)

    assert await listeners._ensure_fafo_banner() is created
    created.pin.assert_awaited_once_with(reason="FAFO honeypot banner")
    assert listeners._fafo_message_id == 808


async def test_update_fafo_banner_count_branches(mock_bot: MagicMock) -> None:
    listeners = _make_listeners(mock_bot)
    banner = MagicMock(spec=discord.Message)
    banner.edit = AsyncMock()
    listeners._ensure_fafo_banner = AsyncMock(return_value=banner)

    banner.components = []
    await listeners._update_fafo_banner()
    first_view = banner.edit.await_args.kwargs["view"]
    assert first_view.children[0].label == "🍯 Timeouts & Kicks: 1"

    banner.components = [object()]
    await listeners._update_fafo_banner()
    banner.components = [SimpleNamespace(children=[])]
    await listeners._update_fafo_banner()
    banner.components = [SimpleNamespace(children=[object()])]
    await listeners._update_fafo_banner()
    banner.components = [SimpleNamespace(children=[SimpleNamespace(label="")])]
    await listeners._update_fafo_banner()
    banner.components = [SimpleNamespace(children=[SimpleNamespace(label="no digits")])]
    await listeners._update_fafo_banner()
    banner.components = [SimpleNamespace(children=[SimpleNamespace(label="🍯 Timeouts & Kicks: 4")])]
    await listeners._update_fafo_banner()
    last_view = banner.edit.await_args.kwargs["view"]
    assert last_view.children[0].label == "🍯 Timeouts & Kicks: 5"


async def test_apply_honeypot_action_kick_and_ban(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    listeners = _make_listeners(mock_bot)
    member = member_factory(user_id=1001)
    member.guild = MagicMock()
    member.guild.name = "PESU"
    member.ban = AsyncMock()
    source = MagicMock(spec=discord.Message)
    source.channel = mock_bot.config.honeypot_channel
    source.channel.id = 1525332571674902738

    with patch("src.cogs.events.helpers.ug.send_dm_safely", AsyncMock(return_value=True)) as dm:
        assert await listeners._apply_honeypot_action(member, source) == "Timed out & Kicked"
        member.timeout.assert_awaited()
        member.kick.assert_awaited()
        member.ban.assert_not_called()
        dm.assert_awaited()

        listeners.HONEYPOT_ACTION = "ban"
        member.timeout.reset_mock()
        member.kick.reset_mock()
        assert await listeners._apply_honeypot_action(member, source) == "Banned"
        member.ban.assert_awaited()
        member.kick.assert_not_called()
        member.timeout.assert_not_called()
