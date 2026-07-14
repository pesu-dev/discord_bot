from __future__ import annotations

import discord
from discord import app_commands

from src.cogs.eng import EngGroups
from src.utils import decorators as bot_decorators
from src.utils.cogs import COGS_PACKAGE, discover_cog_extensions, get_cogs_dir, resolve_cog_extension


class EngCommands:
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
        unixtmstmp = int(self.client.startTime)
        await interaction.followup.send(content=f"Bot was started <t:{unixtmstmp}:R> \ni.e., on <t:{unixtmstmp}:f>")

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

    async def _reload_single_cog(self, interaction: discord.Interaction, cog: str) -> None:
        try:
            extension = resolve_cog_extension(cog)
        except ValueError as e:
            await interaction.followup.send(content=str(e), ephemeral=True)
            return

        try:
            await self.client.reload_extension(extension)
            self.client.logger.info(f"Reloaded cog: {extension}")
            await interaction.followup.send(
                content=f"Successfully reloaded cog: `{extension}`",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.followup.send(
                content=f"Failed to reload cog `{extension}`: {str(e)}",
                ephemeral=True,
            )

    async def _reload_all_cogs(self, interaction: discord.Interaction) -> None:
        success = []
        failed = []

        extensions = discover_cog_extensions(get_cogs_dir(), COGS_PACKAGE)

        for cog_name in extensions:
            try:
                await self.client.unload_extension(cog_name)
                self.client.logger.info(f"Unloaded cog: {cog_name}")
            except Exception:
                pass

        for cog_name in extensions:
            try:
                await self.client.load_extension(cog_name)
                self.client.logger.info(f"Reloaded cog: {cog_name}")
                success.append(cog_name)
            except Exception as e:
                failed.append((cog_name, str(e)))

        response = f"Reloaded {len(success)} cogs successfully."
        if failed:
            response += f"\nFailed to reload {len(failed)} cogs:"
            for cog_name, error in failed:
                response += f"\n- `{cog_name}`: {error[:100]}{'...' if len(error) > 100 else ''}"

        await interaction.followup.send(content=response, ephemeral=True)
