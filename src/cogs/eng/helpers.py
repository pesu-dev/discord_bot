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
                content=f"Reloaded 1 cog successfully.\n- `{extension}`",
                ephemeral=True,
            )
        except Exception as e:
            error = f"{type(e).__name__}: {e}"
            self.client.logger.error(f"Failed to reload cog '{extension}': {error}")
            truncated = f"{error[:100]}{'...' if len(error) > 100 else ''}"
            await interaction.followup.send(
                content=f"Failed to reload 1 cog:\n- `{extension}`: {truncated}",
                ephemeral=True,
            )

    async def _reload_all_cogs(self, interaction: discord.Interaction) -> None:
        success: list[str] = []
        unload_failed: list[tuple[str, str]] = []
        load_failed: list[tuple[str, str]] = []

        extensions = discover_cog_extensions(get_cogs_dir(), COGS_PACKAGE)

        for cog_name in extensions:
            try:
                await self.client.unload_extension(cog_name)
                self.client.logger.info(f"Unloaded cog: {cog_name}")
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                unload_failed.append((cog_name, error))
                self.client.logger.warning(f"Failed to unload cog '{cog_name}' before reload: {error}")

        for cog_name in extensions:
            try:
                await self.client.load_extension(cog_name)
                self.client.logger.info(f"Reloaded cog: {cog_name}")
                success.append(cog_name)
            except Exception as e:
                error = f"{type(e).__name__}: {e}"
                load_failed.append((cog_name, error))
                self.client.logger.error(f"Failed to load cog '{cog_name}' during reload: {error}")

        lines = [f"Reloaded {len(success)} cogs successfully."]
        if unload_failed:
            lines.append(f"Failed to unload {len(unload_failed)} cogs:")
            lines.extend(
                f"- `{cog_name}`: {error[:100]}{'...' if len(error) > 100 else ''}" for cog_name, error in unload_failed
            )
        if load_failed:
            lines.append(f"Failed to load {len(load_failed)} cogs:")
            lines.extend(
                f"- `{cog_name}`: {error[:100]}{'...' if len(error) > 100 else ''}" for cog_name, error in load_failed
            )

        await interaction.followup.send(content="\n".join(lines), ephemeral=True)
