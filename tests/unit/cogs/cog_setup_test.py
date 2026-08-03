from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch


async def test_cog_setups(mock_bot: MagicMock) -> None:
    """Each cog package exposes a setup() that registers with the bot."""
    mock_bot.add_cog = AsyncMock()
    mock_bot.add_view = MagicMock()
    mock_bot.tree = MagicMock()
    mock_bot.tree.add_command = MagicMock()

    from src.cogs.eng import setup as eng_setup
    from src.cogs.events import setup as events_setup
    from src.cogs.general import setup as general_setup
    from src.cogs.help import setup as help_setup

    with patch(
        "src.cogs.anon.SlashAnon.__init__",
        lambda self, client: setattr(self, "client", client) or setattr(self, "tasks", []),
    ):
        from src.cogs.anon import setup as anon_setup

        await anon_setup(mock_bot)

    with patch(
        "src.cogs.mod.SlashMod.__init__",
        lambda self, client: (
            setattr(self, "client", client) or setattr(self, "tasks", []) or setattr(self, "ctx_menu", MagicMock())
        ),
    ):
        from src.cogs.mod import setup as mod_setup

        await mod_setup(mock_bot)

    await eng_setup(mock_bot)
    await events_setup(mock_bot)
    await general_setup(mock_bot)
    await help_setup(mock_bot)
    assert mock_bot.add_cog.await_count >= 5
