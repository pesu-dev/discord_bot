from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext.commands import Cog

from src.cogs.events.helpers import EventHelpers
from src.cogs.events.listeners import EventListeners

if TYPE_CHECKING:
    from src.bot import DiscordBot


class Events(EventHelpers, EventListeners, Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client


async def setup(client: DiscordBot) -> None:
    await client.add_cog(Events(client))
