from __future__ import annotations

from typing import TYPE_CHECKING

from src.utils.general import COGS_PACKAGE, discover_cog_extensions, get_cogs_dir, resolve_cog_extension

if TYPE_CHECKING:
    import discord

    from src.bot import DiscordBot


class EngHelpers:
    client: DiscordBot

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
