from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import respx

from src.cogs.general.commands import GeneralCommands
from src.cogs.general.components import RoleSelect
from src.cogs.general.helpers import ONBOARDING_CHECKLIST, GeneralHelpers, LinkMessage
from tests.helpers import get_callback

if TYPE_CHECKING:
    import pytest

    from tests.conftest import InteractionFactory, MemberFactory


async def test_link_invokes_orchestration(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = GeneralCommands()
    cmd.client = mock_bot
    member = member_factory()
    interaction = interaction_factory(user=member)
    with patch.object(cmd, "link_account", AsyncMock(return_value=("User linked successfully", None))) as link_account:
        await get_callback(cmd.link)(cmd, interaction, "PES1UG21CS001", "secret")
    link_account.assert_awaited_once_with(member, "PES1UG21CS001", "secret")
    interaction.followup.send.assert_awaited_once_with(content="User linked successfully", ephemeral=True)


async def test_link_onboarding_incomplete_sends_checklist(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = GeneralCommands()
    cmd.client = mock_bot
    member = member_factory()
    interaction = interaction_factory(user=member)
    with patch.object(
        cmd, "link_account", AsyncMock(return_value=(LinkMessage.ONBOARDING_INCOMPLETE, ONBOARDING_CHECKLIST))
    ):
        await get_callback(cmd.link)(cmd, interaction, "PES1UG21CS001", "secret")
    assert interaction.followup.send.await_count == 2
    assert interaction.followup.send.await_args_list[0].kwargs["content"] == LinkMessage.ONBOARDING_INCOMPLETE
    assert interaction.followup.send.await_args_list[1].kwargs["content"] == ONBOARDING_CHECKLIST


async def test_info_with_roles(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = GeneralCommands()
    cmd.client = mock_bot
    guild = MagicMock(spec=discord.Guild)
    default_role = MagicMock(spec=discord.Role)
    default_role.id = 1
    guild.default_role = default_role
    role = MagicMock(spec=discord.Role)
    role.id = 2
    role.mention = "<@&2>"
    user = member_factory(roles=[default_role, role])
    user.name = "alice"
    user.created_at = datetime(2020, 1, 1, tzinfo=UTC)
    user.joined_at = datetime(2021, 1, 1, tzinfo=UTC)
    interaction = interaction_factory(guild=guild)
    interaction.guild = guild
    await get_callback(cmd.info)(cmd, interaction, user)
    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert embed.title == "User Info"
    assert any(f.name == "Join" for f in embed.fields)
    assert any(f.name == "Roles" and "<@&2>" in f.value for f in embed.fields)


async def test_info_truncates_long_roles(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = GeneralCommands()
    cmd.client = mock_bot
    guild = MagicMock(spec=discord.Guild)
    default_role = MagicMock(spec=discord.Role)
    default_role.id = 1
    guild.default_role = default_role
    long_role = MagicMock(spec=discord.Role)
    long_role.id = 2
    long_role.mention = "x" * 1100
    user = member_factory(roles=[default_role, long_role])
    user.name = "bob"
    user.created_at = datetime(2020, 1, 1, tzinfo=UTC)
    user.joined_at = None
    interaction = interaction_factory(guild=guild)
    interaction.guild = guild
    await get_callback(cmd.info)(cmd, interaction, user)
    roles_field = next(f for f in interaction.followup.send.await_args.kwargs["embed"].fields if f.name == "Roles")
    assert roles_field.value.endswith("...")
    assert len(roles_field.value) == 1024


async def test_count_server_stats(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = GeneralCommands()
    cmd.client = mock_bot
    guild = MagicMock(spec=discord.Guild)
    guild.member_count = 100
    mock_bot.config.linked_role.members = [MagicMock(), MagicMock()]
    human = MagicMock(bot=False)
    bot_member = MagicMock(bot=True)
    channel = MagicMock()
    channel.members = [human, bot_member]
    interaction = interaction_factory(guild=guild, channel=channel)
    interaction.guild = guild
    interaction.channel = channel
    await get_callback(cmd.count)(cmd, interaction, rolelist=None)
    content = interaction.followup.send.await_args.kwargs["content"]
    assert "Server Stats" in content
    assert "`100`" in content


async def test_count_roles_intersection(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = GeneralCommands()
    cmd.client = mock_bot
    m1, m2, m3 = MagicMock(), MagicMock(), MagicMock()
    role_a = MagicMock(spec=discord.Role)
    role_a.name = "CSE"
    role_a.members = [m1, m2]
    role_b = MagicMock(spec=discord.Role)
    role_b.name = "RR"
    role_b.members = [m2, m3]
    guild = MagicMock(spec=discord.Guild)
    guild.member_count = 10
    guild.roles = [role_a, role_b]
    mock_bot.config.linked_role.members = []
    channel = MagicMock()
    channel.members = []
    interaction = interaction_factory(guild=guild, channel=channel)
    interaction.guild = guild
    interaction.channel = channel
    await get_callback(cmd.count)(cmd, interaction, rolelist="CSE & RR")
    content = interaction.followup.send.await_args.kwargs["content"]
    assert content.startswith("1 person has")


async def test_count_no_roles_found(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = GeneralCommands()
    cmd.client = mock_bot
    guild = MagicMock(spec=discord.Guild)
    guild.member_count = 5
    guild.roles = []
    mock_bot.config.linked_role.members = []
    channel = MagicMock()
    channel.members = []
    interaction = interaction_factory(guild=guild, channel=channel)
    interaction.guild = guild
    interaction.channel = channel
    await get_callback(cmd.count)(cmd, interaction, rolelist="Nope")
    assert interaction.followup.send.await_count == 2
    assert "No roles found" in interaction.followup.send.await_args_list[0].kwargs["content"]


async def test_spotify_listening(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = GeneralCommands()
    cmd.client = mock_bot
    member = member_factory()
    activity = MagicMock(spec=discord.Spotify)
    activity.title = "Song"
    activity.artist = "Artist"
    activity.track_url = "https://open.spotify.com/track/1"
    member.activities = [activity]
    guild = MagicMock(spec=discord.Guild)
    guild.get_member = MagicMock(return_value=member)
    interaction = interaction_factory(user=member, guild=guild)
    interaction.guild = guild
    await get_callback(cmd.spotify)(cmd, interaction, user=None)
    content = interaction.followup.send.await_args.kwargs["content"]
    assert "Song" in content
    assert "Artist" in content


async def test_spotify_not_found_and_no_activity(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = GeneralCommands()
    cmd.client = mock_bot
    guild = MagicMock(spec=discord.Guild)
    guild.get_member = MagicMock(return_value=None)
    interaction = interaction_factory(guild=guild)
    interaction.guild = guild
    await get_callback(cmd.spotify)(cmd, interaction, user=None)
    assert "User not found" in interaction.followup.send.await_args.kwargs["content"]

    member = member_factory()
    member.activities = []
    guild.get_member = MagicMock(return_value=member)
    interaction.followup.send.reset_mock()
    await get_callback(cmd.spotify)(cmd, interaction, user=None)
    assert "No spotify" in interaction.followup.send.await_args.kwargs["content"]


async def test_addroles_sends_view(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = GeneralCommands()
    cmd.client = mock_bot
    channel = MagicMock(spec=discord.TextChannel)
    channel.mention = "<#9>"
    channel.send = AsyncMock()
    interaction = interaction_factory()
    await get_callback(cmd.addroles_command)(cmd, interaction, channel=channel)
    channel.send.assert_awaited()
    assert "Role selection sent" in interaction.followup.send.await_args.kwargs["content"]


async def test_addroles_rejects_non_text(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = GeneralCommands()
    cmd.client = mock_bot
    interaction = interaction_factory()
    interaction.channel = MagicMock()  # not a TextChannel
    await get_callback(cmd.addroles_command)(cmd, interaction, channel=None)
    assert "text channel" in interaction.followup.send.await_args.kwargs["content"]


async def test_pride_with_and_without_link(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = GeneralCommands()
    cmd.client = mock_bot
    message = MagicMock()
    message.reply = AsyncMock()
    channel = MagicMock()
    channel.fetch_message = AsyncMock(return_value=message)
    interaction = interaction_factory(channel=channel)
    interaction.channel = channel
    await get_callback(cmd.pride)(cmd, interaction, link="https://discord.com/channels/1/2/99")
    message.reply.assert_awaited()

    channel.fetch_message = AsyncMock(side_effect=discord.NotFound(MagicMock(), "x"))
    interaction.followup.send.reset_mock()
    await get_callback(cmd.pride)(cmd, interaction, link="bad/link/1")
    contents = [c.kwargs.get("content", "") for c in interaction.followup.send.await_args_list]
    assert any("tenor.com" in (content or "") for content in contents)


async def test_pride_no_link(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = GeneralCommands()
    cmd.client = mock_bot
    interaction = interaction_factory()
    await get_callback(cmd.pride)(cmd, interaction, link=None)
    assert any("tenor.com" in (c.kwargs.get("content") or "") for c in interaction.followup.send.await_args_list)


async def test_ask_exception(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASKPESU_API", "https://askpesu.test/api")
    cmd = GeneralCommands()
    cmd.client = mock_bot
    interaction = interaction_factory()
    with patch("src.cogs.general.commands.httpx.AsyncClient") as client_cls:
        client_cls.return_value.__aenter__.side_effect = RuntimeError("network down")
        await get_callback(cmd.ask)(cmd, interaction, "q")
    assert "embed" in interaction.followup.send.await_args.kwargs


async def test_faq_full_flow(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = GeneralCommands()
    cmd.client = mock_bot
    cmd.cached_data = {
        "Campus": [
            {"question": "Where?", "answer": "https://example.com)"},
            {"question": "When?", "answer": "https://example.com/when"},
        ]
    }
    interaction = interaction_factory()

    await get_callback(cmd.faq)(cmd, interaction, category=None, question=None)
    assert "reddit.com" in interaction.followup.send.await_args.kwargs["content"]

    interaction.followup.send.reset_mock()
    await get_callback(cmd.faq)(cmd, interaction, category=None, question="Where?")
    assert "category" in interaction.followup.send.await_args.kwargs["content"].lower()

    interaction.followup.send.reset_mock()
    await get_callback(cmd.faq)(cmd, interaction, category="Campus", question=None)
    assert "embed" in interaction.followup.send.await_args.kwargs

    interaction.followup.send.reset_mock()
    await get_callback(cmd.faq)(cmd, interaction, category="Campus", question="Where?")
    assert "Where?" in interaction.followup.send.await_args.kwargs["content"]

    interaction.followup.send.reset_mock()
    await get_callback(cmd.faq)(cmd, interaction, category="Campus", question="Missing")
    assert "not found" in interaction.followup.send.await_args.kwargs["content"].lower()


async def test_faq_autocompletes(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = GeneralCommands()
    cmd.client = mock_bot
    cmd.cached_data = {"Campus": [{"question": "Alpha", "answer": "a"}, {"question": "Beta", "answer": "b"}]}
    interaction = interaction_factory()
    cats = await GeneralCommands.category_autocomplete(cmd, interaction, "cam")
    assert [c.value for c in cats] == ["Campus"]

    interaction.namespace = SimpleNamespace(category=None)
    empty = await GeneralCommands.question_autocomplete(cmd, interaction, "")
    assert empty[0].value == ""

    interaction.namespace = SimpleNamespace(category="Campus")
    qs = await GeneralCommands.question_autocomplete(cmd, interaction, "al")
    assert qs[0].value == "Alpha"


async def test_handle_category_empty(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    helpers = GeneralHelpers()
    helpers.client = mock_bot
    helpers.cached_data = {"Empty": []}
    interaction = interaction_factory()
    await helpers._handle_category_only(interaction, helpers.cached_data, "Empty")
    embed = interaction.followup.send.await_args.kwargs["embed"]
    assert "No questions" in (embed.description or "")


async def test_get_data_caches(mock_bot: MagicMock) -> None:
    helpers = GeneralHelpers()
    helpers.client = mock_bot
    helpers.cached_data = None
    with patch("src.cogs.general.helpers.fetch_faq_data", AsyncMock(return_value={"A": []})):
        first = await helpers.get_data()
        second = await helpers.get_data()
    assert first is second


async def test_role_select_deselect_and_remove(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    select = RoleSelect(mock_bot)
    member = member_factory(roles=[mock_bot.config.linked_role])
    role = MagicMock(spec=discord.Role)
    role.mention = "<@&1>"
    member.roles.append(role)
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = member
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.get_role = MagicMock(return_value=role)
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()

    with patch.object(type(select), "values", property(lambda self: ["0"])):
        await select.callback(interaction)
    assert interaction.followup.send.await_args.kwargs["content"] == "OK"

    interaction.followup.send.reset_mock()
    with patch.object(type(select), "values", property(lambda self: ["778825985361051660"])):
        await select.callback(interaction)
    member.remove_roles.assert_awaited_with(role)


async def test_role_select_missing_role(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    select = RoleSelect(mock_bot)
    member = member_factory(roles=[mock_bot.config.linked_role])
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = member
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.get_role = MagicMock(return_value=None)
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    with patch.object(type(select), "values", property(lambda self: ["778825985361051660"])):
        await select.callback(interaction)
    assert "Role not found" in interaction.followup.send.await_args.kwargs["content"]


async def test_role_select_non_member(mock_bot: MagicMock) -> None:
    select = RoleSelect(mock_bot)
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = MagicMock(spec=discord.User)
    interaction.guild = None
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    with patch.object(type(select), "values", property(lambda self: ["0"])):
        await select.callback(interaction)
    assert "server" in interaction.followup.send.await_args.kwargs["content"].lower()


@respx.mock
async def test_ask_empty_answer_chunk(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    from httpx import Response

    monkeypatch.setenv("ASKPESU_API", "https://askpesu.test/api")
    cmd = GeneralCommands()
    cmd.client = mock_bot
    interaction = interaction_factory()
    respx.post("https://askpesu.test/api").mock(return_value=Response(200, json={"answer": "\n\n"}))
    await get_callback(cmd.ask)(cmd, interaction, "q")
    interaction.followup.send.assert_awaited()
