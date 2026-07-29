from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

import discord

from src.cogs.help.components import HelpEmbeds, HelpSelect, HelpView, NextButton, PrevButton

if TYPE_CHECKING:
    from tests.conftest import InteractionFactory


def _wire_welcome(mock_bot: MagicMock) -> None:
    welcome = MagicMock(spec=discord.TextChannel)
    welcome.mention = "<#welcome>"
    mock_bot.config.get_channel = MagicMock(return_value=welcome)


def test_help_embeds_pages(mock_bot: MagicMock) -> None:
    _wire_welcome(mock_bot)
    embeds = HelpEmbeds(mock_bot)
    assert "anon" in embeds.pages
    assert "mod" in embeds.pages
    assert len(embeds.unlink) == 1
    assert len(embeds.pages["general"]) == 3
    assert len(embeds.pages["eng"]) == 2
    general_field_names = [field.name for embed in embeds.pages["general"] for field in embed.fields]
    assert "Link your Account" not in general_field_names
    assert "Toggle Role" in general_field_names


def test_help_view_get_embed_and_nav(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    _wire_welcome(mock_bot)
    interaction = interaction_factory()
    view = HelpView(interaction, mock_bot, category="general", page=0)
    embed = view.get_embed()
    assert "Page 1/" in (embed.footer.text or "")
    assert any(isinstance(item, HelpSelect) for item in view.children)
    assert any(isinstance(item, PrevButton) for item in view.children)
    assert any(isinstance(item, NextButton) for item in view.children)


async def test_help_select_changes_category(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    _wire_welcome(mock_bot)
    interaction = interaction_factory()
    view = HelpView(interaction, mock_bot, category="anon", page=0)
    select = next(item for item in view.children if isinstance(item, HelpSelect))
    select_interaction = interaction_factory()
    select_interaction.response.edit_message = AsyncMock()
    with patch.object(type(select), "values", property(lambda self: ["mod"])):
        await select.callback(select_interaction)
    assert view.category == "mod"
    assert view.page == 0
    select_interaction.response.edit_message.assert_awaited()


async def test_prev_next_buttons(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    _wire_welcome(mock_bot)
    interaction = interaction_factory()
    view = HelpView(interaction, mock_bot, category="general", page=1)
    prev = next(item for item in view.children if isinstance(item, PrevButton))
    next_btn = next(item for item in view.children if isinstance(item, NextButton))
    assert prev.disabled is False

    nav_interaction = interaction_factory()
    nav_interaction.response.edit_message = AsyncMock()
    await next_btn.callback(nav_interaction)
    assert view.page == 2

    await prev.callback(nav_interaction)
    assert view.page == 1


async def test_prev_at_start_and_next_at_end(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    _wire_welcome(mock_bot)
    interaction = interaction_factory()
    view = HelpView(interaction, mock_bot, category="anon", page=0)
    prev = next(item for item in view.children if isinstance(item, PrevButton))
    next_btn = next(item for item in view.children if isinstance(item, NextButton))
    assert prev.disabled is True
    assert next_btn.disabled is True

    nav = interaction_factory()
    nav.response.edit_message = AsyncMock()
    await prev.callback(nav)
    assert view.page == 0
    await next_btn.callback(nav)
    assert view.page == 0
    nav.response.edit_message.assert_not_awaited()


async def test_help_view_on_timeout(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    _wire_welcome(mock_bot)
    interaction = interaction_factory()
    view = HelpView(interaction, mock_bot, category="eng", page=0)
    view.message = MagicMock()
    view.message.edit = AsyncMock()
    await view.on_timeout()
    assert all(getattr(item, "disabled", False) for item in view.children if hasattr(item, "disabled"))
    view.message.edit.assert_awaited()


async def test_help_view_on_timeout_message_gone(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    _wire_welcome(mock_bot)
    interaction = interaction_factory()
    view = HelpView(interaction, mock_bot, category="eng", page=0)
    view.message = MagicMock()
    view.message.edit = AsyncMock(side_effect=discord.NotFound(MagicMock(), "gone"))
    await view.on_timeout()
