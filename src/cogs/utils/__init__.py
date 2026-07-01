from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.bot import DiscordBot


async def setup(client: DiscordBot) -> None:
    from src.cogs.utils.cog import SlashUtils

    await client.add_cog(
        SlashUtils(client),
        guild=client.config.guild_object,
    )
