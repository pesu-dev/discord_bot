from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from discord.ext import tasks
from discord.ext.commands import Cog

from src.cogs.anon.commands import AnonCommands
from src.cogs.anon.groups import AnonGroups
from src.utils import general as ug

if TYPE_CHECKING:
    from src.bot import DiscordBot


class SlashAnon(AnonGroups, AnonCommands, Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client
        self.tasks = [self.check_anon_mutes_loop, self.clear_anon_cache_loop]
        for task in self.tasks:
            if not task.is_running():
                task.start()

    async def cog_unload(self) -> None:
        for task in self.tasks:
            task.cancel()

    @Cog.listener()
    async def on_ready(self) -> None:
        await self.client.wait_until_ready()
        for task in self.tasks:
            if not task.is_running():
                task.start()

    @tasks.loop(seconds=30)
    async def check_anon_mutes_loop(self) -> None:
        now = datetime.now(UTC)
        expired = await self.client.stores.anon_mutes.find_expired(now, limit=100)
        for mute in expired:
            if mute.id is None:
                continue
            await self.client.stores.anon_mutes.mark_unmuted(mute.id, unmuted_at=now)
            user = await self.client.fetch_user(int(mute.discord_user_id))
            if user:
                embed = ug.build_embed(
                    title="Notification",
                    description="Your anon messaging mute has expired",
                    color=discord.Color.green(),
                )
                await ug.send_dm_safely(user, embed)

    @check_anon_mutes_loop.before_loop
    async def before_check_anon_mutes_loop(self) -> None:
        await self.client.wait_until_ready()

    @tasks.loop(seconds=10)
    async def clear_anon_cache_loop(self) -> None:
        if self.client.anon_cache:
            current_time = datetime.now(UTC)
            min_time = 86400
            for key, value in self.client.anon_cache.items():
                self.client.anon_cache[key] = [
                    msg for msg in value if (current_time - msg["timestamp"]).total_seconds() < min_time
                ]

    @clear_anon_cache_loop.before_loop
    async def before_clear_anon_cache_loop(self) -> None:
        await self.client.wait_until_ready()


async def setup(client: DiscordBot) -> None:
    await client.add_cog(SlashAnon(client), guild=client.config.guild_object)
