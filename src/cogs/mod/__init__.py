from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import tasks
from discord.ext.commands import Cog

from src.cogs.mod.anon import AnonModCommands
from src.cogs.mod.commands import ModCommands
from src.cogs.mod.groups import ModGroups
from src.cogs.mod.link import LinkCommands
from src.utils import general as ug

if TYPE_CHECKING:
    from src.bot import DiscordBot


class SlashMod(ModGroups, ModCommands, LinkCommands, AnonModCommands, Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client
        self.ctx_menu = app_commands.ContextMenu(
            name="Ban this anon",
            callback=self.anon_ban_from_context_menu,
        )

        self.tasks = [self.check_mutes_loop]
        for task in self.tasks:
            if not task.is_running():
                task.start()

    async def cog_unload(self) -> None:
        for task in self.tasks:
            task.cancel()

    @tasks.loop(seconds=30)
    async def check_mutes_loop(self) -> None:
        now = datetime.now(UTC)
        expired_mutes = await self.client.stores.mutes.find_expired(now, limit=100)

        guild = self.client.config.guild
        for mute in expired_mutes:
            if mute.id is None:
                continue
            try:
                member = await guild.fetch_member(mute.user_id)
            except discord.NotFound:
                await self.client.stores.mutes.mark_unmuted(
                    mute.id,
                    unmute_time=now,
                    unmute_type="auto_member_left",
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

            await self.client.stores.mutes.mark_unmuted(
                mute.id,
                unmute_time=now,
                unmute_type="loop_auto",
            )

            channel = guild.get_channel(mute.channel_id)
            if not isinstance(channel, discord.TextChannel | discord.Thread):
                continue

            try:
                await channel.send(
                    content=member.mention,
                    embed=ug.build_embed(
                        title="Unmute",
                        color=discord.Color.green(),
                        fields=[{"name": "Unmuted user", "value": f"{member.mention} welcome back"}],
                    ),
                )
            except discord.HTTPException:
                pass

            try:
                await self._send_mod_log(
                    ug.build_embed(
                        title="Unmute",
                        color=discord.Color.green(),
                        fields=[{"name": "Unmuted user", "value": f"{member.mention}\nModerator: Auto"}],
                    )
                )
            except discord.HTTPException:
                pass

    @check_mutes_loop.before_loop
    async def before_check_mutes_loop(self) -> None:
        await self.client.wait_until_ready()


async def setup(client: DiscordBot) -> None:
    cog = SlashMod(client)
    await client.add_cog(cog, guild=client.config.guild_object)
    client.tree.add_command(
        cog.ctx_menu,
        guild=client.config.guild_object,
    )
