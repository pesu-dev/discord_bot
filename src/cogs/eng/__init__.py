from __future__ import annotations

from typing import TYPE_CHECKING

from discord import app_commands

if TYPE_CHECKING:
    from src.bot import DiscordBot


class EngGroups:
    eng = app_commands.Group(name="eng", description="Bot engineering commands")


async def setup(client: DiscordBot) -> None:
    from src.cogs.eng.cog import SlashEng

    await client.add_cog(
        SlashEng(client),
        guild=client.config.guild_object,
    )
