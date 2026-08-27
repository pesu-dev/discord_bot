from __future__ import annotations

from typing import TYPE_CHECKING

from discord.ext import tasks
from discord.ext.commands import Cog

from src.cogs.eng.commands import EngCommands
from src.cogs.eng.groups import EngGroups
from src.cogs.eng.mongo import EngMongoCommands

if TYPE_CHECKING:
    from src.bot import DiscordBot


class SlashEng(EngGroups, EngCommands, EngMongoCommands, Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client
        self.tasks = [self.expire_eng_mongo_loop]
        for task in self.tasks:
            if not task.is_running():
                task.start()

    async def cog_unload(self) -> None:
        for task in self.tasks:
            task.cancel()

    @tasks.loop(seconds=60)
    async def expire_eng_mongo_loop(self) -> None:
        await self._expire_eng_mongo_users()

    @expire_eng_mongo_loop.before_loop
    async def before_expire_eng_mongo_loop(self) -> None:
        await self.client.wait_until_ready()


async def setup(client: DiscordBot) -> None:
    await client.add_cog(
        SlashEng(client),
        guild=client.config.guild_object,
    )
