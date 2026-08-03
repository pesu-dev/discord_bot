from __future__ import annotations

import asyncio
from typing import TYPE_CHECKING

from discord.ext.commands import Cog

from src.cogs.events.listeners import EventListeners

if TYPE_CHECKING:
    from src.bot import DiscordBot


class Events(EventListeners, Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client
        self._fafo_lock = asyncio.Lock()
        self._fafo_message_id: int | None = None


async def setup(client: DiscordBot) -> None:
    await client.add_cog(Events(client))
