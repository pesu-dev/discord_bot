from __future__ import annotations

import datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.cogs.anon import AnonGroups
from src.cogs.anon.bans import BanCommands
from src.cogs.anon.messaging import MessagingCommands
from src.utils import general as ug

if TYPE_CHECKING:
    from src.bot import DiscordBot


class SlashAnon(AnonGroups, MessagingCommands, BanCommands, commands.Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client
        self.anon_cache = {}
        self.ctx_menu = app_commands.ContextMenu(
            name="Ban this anon",
            callback=self.anon_ban_from_context_menu,
        )
        self.tasks = [self.check_anon_bans_loop, self.clear_anon_cache_loop]
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

    async def _check_server_permissions(self, interaction: discord.Interaction) -> bool:
        """Check if interaction is in a server with proper member permissions."""
        if not isinstance(interaction.user, discord.Member) or not interaction.guild:
            await interaction.followup.send(content="This command can only be used in a server", ephemeral=True)
            return False
        return True

    async def _check_mod_permissions(self, interaction: discord.Interaction) -> bool:
        """Check if user has moderator permissions."""
        if not isinstance(interaction.user, discord.Member):
            return False
        if not self.client.config.has_mod_permissions(interaction.user):
            await interaction.followup.send(content="You ain't authorised to run this command", ephemeral=True)
            return False
        return True

    async def _check_text_channel_permissions(self, interaction: discord.Interaction) -> bool:
        """Check if interaction is in a text channel with proper permissions."""
        if (
            not isinstance(interaction.user, discord.Member)
            or not isinstance(interaction.channel, discord.TextChannel)
            or not interaction.guild
        ):
            await interaction.followup.send(content="This command can only be used in a text channel", ephemeral=True)
            return False
        return True

    async def _check_user_anon_ban(self, user_id: str) -> dict | None:
        """Check if user is banned from anon messaging."""
        return await self.client.anonban_collection.find_one({"userId": user_id, "active": True})

    async def _validate_and_parse_time(self, interaction: discord.Interaction, time_str: str) -> int | None:
        """Validate and parse time string, return seconds or None if invalid."""
        try:
            seconds = ug.parse_time(time_str)
            if seconds <= 10:
                await interaction.followup.send(
                    content="You can't ban someone for less than 10 seconds", ephemeral=True
                )
                return None
            return seconds
        except ValueError:
            await interaction.followup.send(
                content=(
                    "Mention the proper amount of time to be muted\nAccepted Time Format: Should end with `d/h/m/s`"
                ),
                ephemeral=True,
            )
            return None

    def _find_user_from_message(self, message_id: str, guild: discord.Guild) -> discord.Member | None:
        """Find the user who sent an anonymous message based on message ID."""
        for user_id, messages in self.anon_cache.items():
            for message in messages:
                if str(message_id) == message["message_id"]:
                    return guild.get_member(int(user_id))
        return None

    def _create_notification_embed(
        self, title: str, description: str, color: discord.Color, fields: list[dict] | None = None
    ) -> discord.Embed:
        """Create a standardized notification embed."""
        embed = discord.Embed(title=title, description=description, color=color)
        if fields:
            for field in fields:
                embed.add_field(name=field["name"], value=field["value"], inline=field.get("inline", False))
        embed.timestamp = datetime.datetime.now(datetime.UTC)
        embed.set_footer(text="PESU Bot")
        return embed

    async def _send_dm_safely(self, user: discord.User | discord.Member, embed: discord.Embed) -> bool:
        """Send DM to user with error handling. Returns True if successful."""
        try:
            await user.send(embed=embed)
            return True
        except (discord.Forbidden, discord.HTTPException):
            return False

    async def _handle_ban_message_link(self, interaction: discord.Interaction, link: str) -> discord.Member | None:
        """Handle message link validation and user lookup."""
        if not isinstance(interaction.channel, discord.TextChannel) or not interaction.guild:
            return None

        try:
            ban_msg = await interaction.channel.fetch_message(int(link.split("/")[-1]))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            await interaction.followup.send(content="Could not find the message to ban from", ephemeral=True)
            return None

        user_to_ban = self._find_user_from_message(str(ban_msg.id), interaction.guild)
        if not user_to_ban:
            await interaction.followup.send(
                content="This wasn't an anon message only da what you doing?", ephemeral=True
            )
            return None

        return user_to_ban

    async def _create_and_store_ban(self, user_id: str, reason: str, time_str: str | None = None) -> str:
        """Create ban data and store in database. Returns expiry display string."""
        banned_at = datetime.datetime.now(datetime.UTC)

        if time_str is not None:
            seconds = ug.parse_time(time_str)
            expires_at = banned_at + datetime.timedelta(seconds=seconds)
        else:
            expires_at = None

        ban_data = {
            "userId": user_id,
            "reason": reason,
            "bannedAt": banned_at,
            "expiresAt": expires_at,
            "active": True,
        }

        await self.client.anonban_collection.insert_one(ban_data)
        return "Permanent" if expires_at is None else f"<t:{int(expires_at.timestamp())}:R>"

    @tasks.loop(seconds=30)
    async def check_anon_bans_loop(self) -> None:
        current_time = datetime.datetime.now(datetime.UTC)
        async for ban in self.client.anonban_collection.find(
            {"expiresAt": {"$ne": None, "$lt": current_time}, "active": True}
        ):
            await self.client.anonban_collection.update_one({"_id": ban["_id"]}, {"$set": {"active": False}})
            user = await self.client.fetch_user(ban["userId"])
            if user:
                embed = self._create_notification_embed(
                    title="Notification",
                    description="Your anon messaging ban has expired",
                    color=discord.Color.green(),
                )
                await self._send_dm_safely(user, embed)

    @check_anon_bans_loop.before_loop
    async def before_check_anon_bans_loop(self) -> None:
        await self.client.wait_until_ready()

    @tasks.loop(seconds=10)
    async def clear_anon_cache_loop(self) -> None:
        if self.anon_cache:
            current_time = datetime.datetime.now(datetime.UTC)
            min_time = 86400
            for key, value in self.anon_cache.items():
                self.anon_cache[key] = [
                    msg for msg in value if (current_time - msg["timestamp"]).total_seconds() < min_time
                ]

    @clear_anon_cache_loop.before_loop
    async def before_clear_anon_cache_loop(self) -> None:
        await self.client.wait_until_ready()
