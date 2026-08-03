from __future__ import annotations

from typing import TYPE_CHECKING
from unittest.mock import AsyncMock, MagicMock, patch

from src.cogs.eng.commands import EngCommands
from src.cogs.eng.helpers import EngHelpers
from tests.helpers import get_callback

if TYPE_CHECKING:
    from tests.conftest import InteractionFactory


async def test_reload_single_invalid_cog(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    helpers = EngHelpers()
    helpers.client = mock_bot
    interaction = interaction_factory()
    with patch("src.cogs.eng.helpers.resolve_cog_extension", side_effect=ValueError("unknown cog")):
        await helpers._reload_single_cog(interaction, "nope")
    assert "unknown cog" in interaction.followup.send.await_args.kwargs["content"]


async def test_reload_single_extension_failure(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    helpers = EngHelpers()
    helpers.client = mock_bot
    interaction = interaction_factory()
    mock_bot.reload_extension = AsyncMock(side_effect=RuntimeError("boom" * 40))
    with patch("src.cogs.eng.helpers.resolve_cog_extension", return_value="src.cogs.eng"):
        await helpers._reload_single_cog(interaction, "eng")
    content = interaction.followup.send.await_args.kwargs["content"]
    assert "Failed to reload" in content
    assert "..." in content


async def test_reload_all_cogs_mixed(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    helpers = EngHelpers()
    helpers.client = mock_bot
    interaction = interaction_factory()
    mock_bot.unload_extension = AsyncMock(side_effect=[None, RuntimeError("unload fail")])
    mock_bot.load_extension = AsyncMock(side_effect=[None, RuntimeError("load fail" * 20)])
    with patch("src.cogs.eng.helpers.discover_cog_extensions", return_value=["src.cogs.a", "src.cogs.b"]):
        with patch("src.cogs.eng.helpers.get_cogs_dir"):
            await helpers._reload_all_cogs(interaction)
    content = interaction.followup.send.await_args.kwargs["content"]
    assert "Reloaded 1 cogs successfully" in content
    assert "Failed to unload" in content
    assert "Failed to load" in content


async def test_reload_all_cogs_success(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    helpers = EngHelpers()
    helpers.client = mock_bot
    interaction = interaction_factory()
    mock_bot.unload_extension = AsyncMock()
    mock_bot.load_extension = AsyncMock()
    with patch("src.cogs.eng.helpers.discover_cog_extensions", return_value=["src.cogs.a", "src.cogs.b"]):
        with patch("src.cogs.eng.helpers.get_cogs_dir"):
            await helpers._reload_all_cogs(interaction)
    content = interaction.followup.send.await_args.kwargs["content"]
    assert "Reloaded 2 cogs successfully" in content
    assert "Failed to unload" not in content
    assert "Failed to load" not in content


async def test_eng_reload_dispatches_single(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = EngCommands()
    cmd.client = mock_bot
    interaction = interaction_factory()
    with patch.object(cmd, "_reload_single_cog", new=AsyncMock()) as single:
        await get_callback(cmd.eng_reload)(cmd, interaction, cog="eng")
    single.assert_awaited_once()


async def test_eng_reload_dispatches_all(mock_bot: MagicMock, interaction_factory: InteractionFactory) -> None:
    cmd = EngCommands()
    cmd.client = mock_bot
    interaction = interaction_factory()
    with patch.object(cmd, "_reload_all_cogs", new=AsyncMock()) as all_cogs:
        await get_callback(cmd.eng_reload)(cmd, interaction, cog=None)
    all_cogs.assert_awaited_once()
