from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands

from src.cogs.eng.groups import EngGroups
from src.utils import decorators as bot_decorators

if TYPE_CHECKING:
    from src.bot import DiscordBot


class EngCommands:
    client: DiscordBot

    @EngGroups.eng.command(name="ping", description="Get the bot's latency")
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.handle_command_errors()
    async def eng_ping(self, interaction: discord.Interaction) -> None:
        await interaction.followup.send(content=f"Pong!!!\nPing = `{round(self.client.latency * 1000)}ms`")

    @EngGroups.eng.command(name="uptime", description="Get the bot's uptime")
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.handle_command_errors()
    async def eng_uptime(self, interaction: discord.Interaction) -> None:
        started_at = datetime.fromtimestamp(self.client.start_time, tz=UTC)
        await interaction.followup.send(
            content=(
                f"Bot was started {discord.utils.format_dt(started_at, 'R')} "
                f"\ni.e., on {discord.utils.format_dt(started_at, 'f')}"
            )
        )

    @EngGroups.eng.command(name="support", description="Contribute to bot development")
    @bot_decorators.defer(ephemeral=False)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.handle_command_errors()
    async def eng_support(self, interaction: discord.Interaction) -> None:
        await interaction.followup.send(
            content="You can contribute to the bot here\nhttps://github.com/pesu-dev/discord_bot"
        )

    @EngGroups.eng.command(name="reload", description="Reload all cogs or a specific cog")
    @app_commands.describe(cog="Cog to reload (e.g. mod or src.cogs.mod; leave empty to reload all)")
    @bot_decorators.defer(ephemeral=True)
    @bot_decorators.requires_location(bot_decorators.CommandLocation.GUILD)
    @bot_decorators.requires_roles(bot_decorators.FunctionalRole.BOT_DEV)
    @bot_decorators.handle_command_errors()
    async def eng_reload(self, interaction: discord.Interaction, cog: str | None = None) -> None:
        if cog:
            await self._reload_single_cog(interaction, cog)
        else:
            await self._reload_all_cogs(interaction)
