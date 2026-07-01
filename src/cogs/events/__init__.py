from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from src.bot import DiscordBot


async def setup(client: DiscordBot) -> None:
    from src.cogs.events.cog import Events

    await client.add_cog(Events(client))
