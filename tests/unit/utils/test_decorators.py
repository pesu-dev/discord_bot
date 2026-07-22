from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import MagicMock, patch

import discord

from src.utils import decorators as bot_decorators

if TYPE_CHECKING:
    from tests.conftest import InteractionFactory, MemberFactory


class _Cog:
    def __init__(self, client: MagicMock) -> None:
        self.client = client


def _guild_channel() -> MagicMock:
    channel = MagicMock()
    # Make isinstance(..., Messageable) and guild checks work via patches below.
    channel.guild = MagicMock(spec=discord.Guild)
    return channel


async def test_defer_calls_interaction_response(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    interaction = interaction_factory()

    @bot_decorators.defer(ephemeral=False)
    async def handler(self: _Cog, interaction: discord.Interaction) -> str:
        return "ok"

    result = await handler(_Cog(mock_bot), interaction)
    assert result == "ok"
    interaction.response.defer.assert_awaited_once_with(ephemeral=False)


async def test_requires_location_rejects_non_guild(
    mock_bot: MagicMock, interaction_factory: InteractionFactory
) -> None:
    interaction = interaction_factory()
    interaction.user = MagicMock(spec=discord.User)  # not a Member

    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    async def handler(self: _Cog, interaction: discord.Interaction) -> str:
        return "ok"

    with (
        patch("src.utils.decorators._is_guild_messageable", return_value=True),
        patch("src.utils.decorators._get_member", return_value=None),
    ):
        result = await handler(_Cog(mock_bot), interaction)

    assert result is None
    interaction.followup.send.assert_awaited()
    assert "server" in interaction.followup.send.await_args.kwargs["content"].lower()


async def test_requires_location_guild_ok(
    mock_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    member = member_factory()
    interaction = interaction_factory(user=member)

    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    async def handler(self: _Cog, interaction: discord.Interaction) -> str:
        return "ok"

    with (
        patch("src.utils.decorators._is_guild_messageable", return_value=True),
        patch("src.utils.decorators._get_member", return_value=member),
    ):
        assert await handler(_Cog(mock_bot), interaction) == "ok"


async def test_requires_roles_rejects(
    mock_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    member = member_factory(roles=[])
    interaction = interaction_factory(user=member)

    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_roles(bot_decorators.FunctionalRole.MOD)
    async def handler(self: _Cog, interaction: discord.Interaction) -> str:
        return "ok"

    with patch("src.utils.decorators._get_member", return_value=member):
        result = await handler(_Cog(mock_bot), interaction)

    assert result is None
    interaction.followup.send.assert_awaited()


async def test_requires_roles_allows_mod(
    mock_bot: MagicMock, member_factory: MemberFactory, interaction_factory: InteractionFactory
) -> None:
    member = member_factory(roles=[mock_bot.config.mod_role])
    interaction = interaction_factory(user=member)

    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_roles(bot_decorators.FunctionalRole.ADMIN, bot_decorators.FunctionalRole.MOD)
    async def handler(self: _Cog, interaction: discord.Interaction) -> str:
        return "ok"

    with patch("src.utils.decorators._get_member", return_value=member):
        assert await handler(_Cog(mock_bot), interaction) == "ok"


async def test_handle_command_errors_catches(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    interaction = interaction_factory()

    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.handle_command_errors(not_found="missing")
    async def handler(self: _Cog, interaction: discord.Interaction) -> None:
        raise discord.NotFound(MagicMock(), "x")

    result = await handler(_Cog(mock_bot), interaction)
    assert result is None
    interaction.followup.send.assert_awaited()
    assert interaction.followup.send.await_args.kwargs["content"] == "missing"


def test_functional_role_config_attr() -> None:
    assert bot_decorators.FunctionalRole.BOT_DEV.config_attr == "bot_dev_role"


def test_is_guild_and_dm_helpers() -> None:
    # The helpers use isinstance() checks against discord.py concrete types.
    dm = object.__new__(discord.DMChannel)
    assert bot_decorators._is_dm_messageable(dm) is True
    assert bot_decorators._is_guild_messageable(dm) is False
    guild_channel = MagicMock()
    guild_channel.guild = MagicMock(spec=discord.Guild)
    with patch("src.utils.decorators.discord.abc.Messageable", type(guild_channel)):
        assert bot_decorators._is_guild_messageable(guild_channel) is True
    assert bot_decorators._is_dm_messageable(None) is False


async def test_requires_location_dm(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    interaction = interaction_factory()

    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.DM)
    async def handler(self: _Cog, interaction: discord.Interaction) -> str:
        return "dm-ok"

    with patch("src.utils.decorators._is_dm_messageable", return_value=True):
        assert await handler(_Cog(mock_bot), interaction) == "dm-ok"

    with patch("src.utils.decorators._is_dm_messageable", return_value=False):
        assert await handler(_Cog(mock_bot), interaction) is None
