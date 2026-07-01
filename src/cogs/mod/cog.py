from __future__ import annotations

import datetime as dt
from datetime import datetime
from typing import TYPE_CHECKING

import discord
from discord.ext import commands, tasks

from src.cogs.mod import ModGroups
from src.cogs.mod.link import LinkCommands
from src.cogs.mod.moderation import ModerationCommands
from src.utils import general as ug

if TYPE_CHECKING:
    from src.bot import DiscordBot


class SlashMod(ModGroups, ModerationCommands, LinkCommands, commands.Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client

        self.tasks = [self.check_mutes_loop]
        for task in self.tasks:
            if not task.is_running():
                task.start()

    async def cog_unload(self) -> None:
        for task in self.tasks:
            task.cancel()

    @commands.Cog.listener()
    async def on_ready(self) -> None:
        await self.client.wait_until_ready()
        for task in self.tasks:
            if not task.is_running():
                task.start()

    @tasks.loop(seconds=30)
    async def check_mutes_loop(self) -> None:
        now = datetime.now(dt.UTC)
        expired_mutes = await self.client.mute_collection.find({"unmute_time": {"$lte": now}, "active": True}).to_list(
            length=100
        )

        guild = self.client.config.guild
        for mute in expired_mutes:
            try:
                member = await guild.fetch_member(mute["user_id"])
            except discord.NotFound:
                await self.client.mute_collection.update_one(
                    {"_id": mute["_id"]},
                    {
                        "$set": {
                            "active": False,
                            "unmute_time": now,
                            "unmute_type": "auto_member_left",
                        }
                    },
                )
                continue

            muted_role = self.client.config.muted_role
            if muted_role and muted_role in member.roles:
                try:
                    await member.remove_roles(muted_role, reason="Automatic unmute by loop")
                except Exception as e:
                    embed = ug.build_unknown_error_embed(e)
                    bot_logs = self.client.config.bot_logs_channel
                    await bot_logs.send(embed=embed)

            await self.client.mute_collection.update_one(
                {"_id": mute["_id"]},
                {
                    "$set": {
                        "active": False,
                        "unmute_time": now,
                        "unmute_type": "loop_auto",
                    }
                },
            )

            channel = guild.get_channel(mute["channel_id"])
            if not isinstance(channel, discord.TextChannel | discord.Thread):
                continue

            unmute_embed = discord.Embed(title="Unmute", color=discord.Color.green(), timestamp=now)
            unmute_embed.add_field(
                name="Unmuted user",
                value=f"{member.mention} welcome back",
                inline=False,
            )
            unmute_embed.set_footer(text="PESU Bot")
            try:
                await channel.send(content=member.mention, embed=unmute_embed)
            except discord.HTTPException:
                pass

            mod_logs = self.client.config.mod_logs_channel
            unmute_logs_embed = discord.Embed(title="Unmute", color=discord.Color.green(), timestamp=now)

            unmute_logs_embed.add_field(
                name="Unmuted user",
                value=f"{member.mention}\nModerator: Auto",
                inline=False,
            )
            unmute_logs_embed.set_footer(text="PESU Bot")

            try:
                await mod_logs.send(embed=unmute_logs_embed)
            except discord.HTTPException:
                pass

    @check_mutes_loop.before_loop
    async def before_check_mutes_loop(self) -> None:
        await self.client.wait_until_ready()
