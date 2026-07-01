from __future__ import annotations

import discord
from discord import app_commands

from src.cogs.eng import EngGroups
from src.utils import general as ug
from src.utils.cogs import COGS_PACKAGE, discover_cog_extensions, get_cogs_dir, resolve_cog_extension


class EngCommands:
    @EngGroups.eng.command(name="ping", description="Get the bot's latency")
    async def eng_ping(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await interaction.followup.send(content=f"Pong!!!\nPing = `{round(self.client.latency * 1000)}ms`")

    @eng_ping.error
    async def eng_ping_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @EngGroups.eng.command(name="uptime", description="Get the bot's uptime")
    async def eng_uptime(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        unixtmstmp = int(self.client.startTime)
        await interaction.followup.send(content=f"Bot was started <t:{unixtmstmp}:R> \ni.e., on <t:{unixtmstmp}:f>")

    @eng_uptime.error
    async def eng_uptime_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @EngGroups.eng.command(name="support", description="Contribute to bot development")
    async def eng_support(self, interaction: discord.Interaction) -> None:
        await interaction.response.defer()
        await interaction.followup.send(
            content="You can contribute to the bot here\nhttps://github.com/pesu-dev/discord_bot"
        )

    @eng_support.error
    async def eng_support_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))

    @EngGroups.eng.command(name="reload", description="Reload all cogs or a specific cog")
    @app_commands.describe(cog="Cog to reload (e.g. mod or src.cogs.mod; leave empty to reload all)")
    async def eng_reload(self, interaction: discord.Interaction, cog: str | None = None) -> None:
        await interaction.response.defer(ephemeral=True)

        if not isinstance(interaction.user, discord.Member):
            await interaction.followup.send(
                content="This command can only be used by members",
                ephemeral=True,
            )
            return

        if not self.client.config.has_bot_dev_permissions(interaction.user):
            await interaction.followup.send(
                content="You don't have permission to use this command.",
                ephemeral=True,
            )
            return

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

    @eng_reload.error
    async def eng_reload_error(
        self,
        interaction: discord.Interaction,
        error: app_commands.AppCommandError,
    ) -> None:
        await interaction.followup.send(embed=ug.build_unknown_error_embed(error))
