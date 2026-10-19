from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock

from src.cogs.eng.git import EngGitCommands
from src.utils import decorators as bot_decorators

if TYPE_CHECKING:
    from tests.conftest import InteractionFactory, MemberFactory


async def test_eng_git_join_requires_prod_env(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    mock_bot.config.env = bot_decorators.AppEnvironment.DEV
    member = member_factory(roles=[mock_bot.config.dev_engineer_role])
    interaction = interaction_factory(user=member)

    await cmd.join.callback(cmd, interaction, github_username="testuser")
    interaction.followup.send.assert_awaited_once()
    assert "not available in this environment" in interaction.followup.send.await_args.kwargs["content"]


async def test_eng_git_who_requires_prod_env(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    mock_bot.config.env = bot_decorators.AppEnvironment.LOCAL
    member = member_factory(roles=[mock_bot.config.bot_dev_role])
    interaction = interaction_factory(user=member)

    await cmd.who.callback(cmd, interaction, github_user="testuser")
    interaction.followup.send.assert_awaited_once()
    assert "not available in this environment" in interaction.followup.send.await_args.kwargs["content"]


async def test_eng_git_join_allows_prod_env(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    mock_bot.config.env = bot_decorators.AppEnvironment.PROD
    member = member_factory(roles=[mock_bot.config.dev_engineer_role])
    interaction = interaction_factory(user=member)
    mock_bot.stores.git_links.find_one = AsyncMock(return_value=MagicMock())

    await cmd.join.callback(cmd, interaction, github_username="testuser")
    interaction.followup.send.assert_awaited_once()
    content = interaction.followup.send.await_args.args[0]
    assert "already exists" in content


async def test_eng_git_who_allows_prod_env(
    mock_bot: MagicMock, interaction_factory: InteractionFactory, member_factory: MemberFactory
) -> None:
    cmd = EngGitCommands()
    cmd.client = mock_bot
    mock_bot.config.env = bot_decorators.AppEnvironment.PROD
    member = member_factory(roles=[mock_bot.config.bot_dev_role])
    interaction = interaction_factory(user=member)

    await cmd.who.callback(cmd, interaction, member=None, github_user=None)
    interaction.followup.send.assert_awaited_once()
    assert "Please provide either" in interaction.followup.send.await_args.kwargs["content"]
