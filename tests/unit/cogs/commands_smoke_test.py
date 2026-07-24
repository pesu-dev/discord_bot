from __future__ import annotations

from types import SimpleNamespace
from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import discord
import respx
from httpx import Response

from src.cogs.anon.commands import AnonCommands
from src.cogs.eng.commands import EngCommands
from src.cogs.eng.helpers import EngHelpers
from src.cogs.general.commands import GeneralCommands
from src.cogs.general.components import RoleSelect
from src.cogs.general.helpers import GeneralHelpers
from src.cogs.help.commands import HelpCommands
from src.cogs.mod.commands import ModCommands
from tests.helpers import get_callback

if TYPE_CHECKING:
    import pytest

    from tests.conftest import InteractionFactory, MemberFactory


async def test_anon_send_requires_link(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonCommands()
    cmd.client = mock_bot
    mock_bot.stores.links.exists = AsyncMock(return_value=False)
    interaction = interaction_factory(user=member_factory())
    await get_callback(cmd.anon_send)(cmd, interaction, "hello")
    assert "not linked" in interaction.followup.send.await_args.kwargs["content"]


async def test_anon_send_blocked_when_banned(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonCommands()
    cmd.client = mock_bot
    mock_bot.stores.links.exists = AsyncMock(return_value=True)
    mock_bot.stores.anonbans.exists = AsyncMock(return_value=True)
    interaction = interaction_factory(user=member_factory())
    await get_callback(cmd.anon_send)(cmd, interaction, "hello")
    assert "banned" in interaction.followup.send.await_args.kwargs["content"].lower()


async def test_anon_send_success_caches_message(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = AnonCommands()
    cmd.client = mock_bot
    mock_bot.stores.links.exists = AsyncMock(return_value=True)
    mock_bot.stores.anonbans.exists = AsyncMock(return_value=False)
    member = member_factory(user_id=1001)
    interaction = interaction_factory(user=member)
    mock_bot.config.lobby_channel.permissions_for = MagicMock(return_value=SimpleNamespace(send_messages=True))
    sent = MagicMock()
    sent.id = 555
    mock_bot.config.lobby_channel.send = AsyncMock(return_value=sent)

    await get_callback(cmd.anon_send)(cmd, interaction, "secret")
    assert "1001" in mock_bot.anon_cache
    assert mock_bot.anon_cache["1001"][0]["message_id"] == "555"


async def test_anon_vote_stub(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = AnonCommands()
    cmd.client = mock_bot
    interaction = interaction_factory()
    await get_callback(cmd.anon_vote)(cmd, interaction)
    assert "coming soon" in interaction.followup.send.await_args.kwargs["content"].lower()


async def test_eng_ping(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = EngCommands()
    cmd.client = mock_bot
    interaction = interaction_factory()
    await get_callback(cmd.eng_ping)(cmd, interaction)
    content = interaction.followup.send.await_args.kwargs["content"]
    assert "Pong" in content
    assert "42ms" in content


async def test_eng_uptime(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = EngCommands()
    cmd.client = mock_bot
    interaction = interaction_factory()
    await get_callback(cmd.eng_uptime)(cmd, interaction)
    assert "Bot was started" in interaction.followup.send.await_args.kwargs["content"]


async def test_eng_support(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = EngCommands()
    cmd.client = mock_bot
    interaction = interaction_factory()
    await get_callback(cmd.eng_support)(cmd, interaction)
    assert "github.com/pesu-dev/discord_bot" in interaction.followup.send.await_args.kwargs["content"]


async def test_eng_reload_single(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    helpers = EngHelpers()
    helpers.client = mock_bot
    interaction = interaction_factory()
    with patch("src.cogs.eng.helpers.resolve_cog_extension", return_value="src.cogs.eng"):
        mock_bot.reload_extension = AsyncMock()
        await helpers._reload_single_cog(interaction, "eng")
    mock_bot.reload_extension.assert_awaited_with("src.cogs.eng")


async def test_help_unlinked(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = HelpCommands()
    cmd.client = mock_bot
    interaction = interaction_factory(user=member_factory(roles=[]))
    await get_callback(cmd.help_command)(cmd, interaction)
    interaction.followup.send.assert_awaited()
    assert "embed" in interaction.followup.send.await_args.kwargs


async def test_help_linked(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = HelpCommands()
    cmd.client = mock_bot
    interaction = interaction_factory(user=member_factory(roles=[mock_bot.config.linked_role]))
    with patch("src.cogs.help.commands.HelpView") as view_cls:
        view = MagicMock()
        view.get_embed.return_value = MagicMock()
        view_cls.return_value = view
        interaction.followup.send = AsyncMock(return_value=MagicMock())
        await get_callback(cmd.help_command)(cmd, interaction)
    interaction.followup.send.assert_awaited()


async def test_mod_mute_self_too_short(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    member = member_factory(user_id=5)
    interaction = interaction_factory(user=member)
    interaction.user = member
    await get_callback(cmd.mute)(cmd, interaction, member, "30m")
    assert "1 hour" in interaction.followup.send.await_args.kwargs["content"]


async def test_mod_mute_success(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(user_id=1, roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=2, roles=[])
    interaction = interaction_factory(user=mod)
    interaction.user = mod
    mock_bot.stores.mutes.insert_one = AsyncMock()
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    await get_callback(cmd.mute)(cmd, interaction, target, "2h", "noise")
    target.add_roles.assert_awaited_with(mock_bot.config.muted_role)
    mock_bot.stores.mutes.insert_one.assert_awaited()


async def test_mod_unmute(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(roles=[mock_bot.config.mod_role])
    target = member_factory(roles=[mock_bot.config.muted_role])
    interaction = interaction_factory(user=mod)
    mock_bot.stores.mutes.deactivate_active = AsyncMock()
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    await get_callback(cmd.unmute)(cmd, interaction, target)
    target.remove_roles.assert_awaited_with(mock_bot.config.muted_role)
    mock_bot.stores.mutes.deactivate_active.assert_awaited()


async def test_mod_kick(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=9)
    interaction = interaction_factory(user=mod)
    interaction.guild = MagicMock()
    interaction.guild.name = "PESU"
    mock_bot.config.mod_logs_channel.send = AsyncMock()

    await get_callback(cmd.kick)(cmd, interaction, target, "spam")
    target.kick.assert_awaited()


async def test_mod_purge(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    interaction = interaction_factory(user=member_factory(roles=[mock_bot.config.mod_role]))
    interaction.channel = MagicMock(spec=discord.TextChannel)
    interaction.channel.purge = AsyncMock(return_value=[MagicMock(), MagicMock()])
    mock_bot.config.mod_logs_channel.send = AsyncMock()
    await get_callback(cmd.purge)(cmd, interaction, 2)
    interaction.channel.purge.assert_awaited()


async def test_mod_timeout(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = ModCommands()
    cmd.client = mock_bot
    mod = member_factory(roles=[mock_bot.config.mod_role])
    target = member_factory(user_id=3)
    interaction = interaction_factory(user=mod)
    mock_bot.config.mod_logs_channel.send = AsyncMock()
    await get_callback(cmd.timeout_member)(cmd, interaction, target, "10m", "quiet")
    target.timeout.assert_awaited()


@respx.mock
async def test_ask_success_chunks(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASKPESU_API", "https://askpesu.test/api")
    cmd = GeneralCommands()
    cmd.client = mock_bot
    cmd.cached_data = None
    long_answer = "\n".join(["line"] * 300)
    respx.post("https://askpesu.test/api").mock(return_value=Response(200, json={"answer": long_answer}))
    interaction = interaction_factory()
    await get_callback(cmd.ask)(cmd, interaction, "what is pesu?")
    interaction.followup.send.assert_awaited()
    embeds = interaction.followup.send.await_args.kwargs["embeds"]
    assert len(embeds) >= 1


@respx.mock
async def test_ask_http_error(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ASKPESU_API", "https://askpesu.test/api")
    cmd = GeneralCommands()
    cmd.client = mock_bot
    respx.post("https://askpesu.test/api").mock(return_value=Response(500, text="err"))
    interaction = interaction_factory()
    await get_callback(cmd.ask)(cmd, interaction, "q")
    assert "500" in interaction.followup.send.await_args.kwargs["content"]


async def test_faq_invalid_category(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = GeneralCommands()
    cmd.client = mock_bot
    cmd.cached_data = {"Campus": []}
    interaction = interaction_factory()
    await get_callback(cmd.faq)(cmd, interaction, category="Nope")
    assert "Invalid category" in interaction.followup.send.await_args.kwargs["content"]


async def test_general_handle_category_only(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    helpers = GeneralHelpers()
    helpers.client = mock_bot
    helpers.cached_data = None
    interaction = interaction_factory()
    data = {"Campus": [{"question": "Q", "answer": "https://example.com"}]}
    await helpers._handle_category_only(interaction, data, "Campus")
    interaction.followup.send.assert_awaited()


async def test_role_select_requires_linked(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    select = RoleSelect(mock_bot)
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = member_factory(roles=[])
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    with patch.object(type(select), "values", property(lambda self: ["778825985361051660"])):
        await select.callback(interaction)
    content = interaction.followup.send.await_args.kwargs["content"]
    assert "link" in content.lower()


async def test_role_select_add_role(mock_bot: MagicMock, member_factory: MemberFactory) -> None:
    select = RoleSelect(mock_bot)
    member = member_factory(roles=[mock_bot.config.linked_role])
    role = MagicMock(spec=discord.Role)
    role.mention = "<@&1>"
    interaction = MagicMock(spec=discord.Interaction)
    interaction.user = member
    interaction.guild = MagicMock(spec=discord.Guild)
    interaction.guild.get_role = MagicMock(return_value=role)
    interaction.response = MagicMock()
    interaction.response.defer = AsyncMock()
    interaction.followup = MagicMock()
    interaction.followup.send = AsyncMock()
    with patch.object(type(select), "values", property(lambda self: ["778825985361051660"])):
        await select.callback(interaction)
    member.add_roles.assert_awaited_with(role)
