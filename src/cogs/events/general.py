import asyncio
import os
import random
import re
from datetime import datetime

import discord
from discord.ext import commands

from bot import DiscordBot


class Events(commands.Cog):
    def __init__(self, client: DiscordBot) -> None:
        self.client = client

    @staticmethod
    def _filter_reply_mentions(message: discord.Message) -> list[discord.User | discord.Member]:
        """Filter out reply mentions from the mentions list."""
        mentions = message.mentions

        if (
            message.type == discord.MessageType.reply
            and message.reference is not None
            and message.reference.resolved is not None
        ):
            try:
                resolved = message.reference.resolved
                if isinstance(resolved, discord.Message):
                    replied_user = resolved.author
                    if replied_user in mentions:
                        mentions = [m for m in mentions if m.id != replied_user.id]
            except Exception:
                pass

        return mentions

    @staticmethod
    def _create_ghost_ping_embed(title: str) -> discord.Embed:
        """Create a ghost ping embed with common properties."""
        embed = discord.Embed(
            title=title,
            timestamp=datetime.now(),
            color=discord.Color.blue(),
        )
        embed.set_footer(text="PESU Bot")
        return embed

    @staticmethod
    def _add_everyone_ping_field(embed: discord.Embed, message: discord.Message) -> None:
        """Add everyone/here ping field if applicable."""
        if message.mention_everyone:
            embed.add_field(
                name="@everyone/@here pings",
                value=f"{message.author.mention} ghost pinged `@everyone/@here` in {message.channel.mention}",
                inline=False,
            )

    @staticmethod
    def _add_role_ping_fields(embed: discord.Embed, role_mentions: list, message: discord.Message) -> None:
        """Add role ping fields if applicable."""
        if role_mentions:
            ping_list = " ".join(role.mention for role in role_mentions)
            embed.add_field(
                name="Role pings",
                value=f"{message.author.mention} ghost pinged {ping_list} in {message.channel.mention}",
                inline=False,
            )

    @staticmethod
    def _add_member_ping_fields(
        embed: discord.Embed, mentions: list[discord.User | discord.Member], message: discord.Message
    ) -> None:
        """Add member ping fields if applicable."""
        user_mentions = [member for member in mentions if not member.bot]
        if user_mentions:
            ping_list = " ".join(member.mention for member in user_mentions)
            embed.add_field(
                name="Member pings",
                value=f"{message.author.mention} ghost pinged {ping_list} in {message.channel.mention}",
                inline=False,
            )

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        bot_logs = self.client.config.bot_logs_channel
        just_joined = self.client.config.just_joined_role
        await bot_logs.send(f"{member.mention} Joined!!")

        link_record = await self.client.link_collection.find_one({"userId": str(member.id)})
        roles_to_add = [just_joined]
        should_delete_link = bool(link_record and not link_record.get("linkedAt"))

        if link_record and link_record.get("linkedAt") and link_record.get("prn"):
            student_record = await self.client.student_collection.find_one({"prn": link_record.get("prn")})
            if student_record:
                roles_to_add = []
                role_configs = [("YEAR", ["year"]), ("BRANCH", ["branch", "short"]), ("CAMPUS", ["campus", "short"])]
                for role_type, key_path in role_configs:
                    value = student_record
                    for key in key_path:
                        value = value.get(key) if value else None
                    if value and (role := self.client.config.get_role(role_type, value)):
                        roles_to_add.append(role)
                if len(roles_to_add) == 3:
                    roles_to_add.append(self.client.config.linked_role)
                else:
                    roles_to_add = [just_joined]
                    should_delete_link = True
            else:
                should_delete_link = True

        await member.add_roles(*roles_to_add)
        if should_delete_link and link_record:
            await self.client.link_collection.delete_one({"_id": link_record["_id"]})

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        bot_logs = self.client.config.bot_logs_channel
        await bot_logs.send(f"{member.mention} Left!!")

        link_record = await self.client.link_collection.find_one({"userId": str(member.id)})

        if link_record and link_record.get("linkedAt") is None:
            await self.client.link_collection.delete_one({"_id": link_record["_id"]})
            await bot_logs.send(f"Linked record of {member.mention} has been deleted.!")

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        if os.getenv("APP_ENV") == "prod" and random.random() <= 0.2:  # 20% chance and prod deployment
            # Special EC Campus keyword patterns. Only check for words, not internal matches
            patterns = [r"\becc\b", r"\bec campus\b", r"\bec\b"]
            # Normalize message content to handle case insensitive matches
            content = message.content.lower()
            # Check for matches
            if any(re.search(pattern, content) for pattern in patterns):
                gif_url = "https://tenor.com/view/pes-pes-college-pesu-pes-univercity-pes-rr-gif-26661455"
                reply_text = "Did someone mention EC Campus? 👀"
                async with message.channel.typing():
                    await asyncio.sleep(1)
                    await message.reply(reply_text)
                    await message.channel.send(gif_url)

    @commands.Cog.listener()
    async def on_message_delete(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        mentions = message.mentions
        role_mentions = message.role_mentions

        ghost_ping_embed = discord.Embed(
            title="Ghost Ping Alert",
            timestamp=datetime.now(),
            color=discord.Color.blue(),
        )

        if message.mention_everyone:
            ghost_ping_embed.add_field(
                name="@everyone/@here pings",
                value=f"{message.author.mention} ghost pinged `@everyone/@here` in {message.channel.mention}",
                inline=False,
            )

        if role_mentions:
            ping_list = ""
            for role in role_mentions:
                ping_list += role.mention + " "
            ghost_ping_embed.add_field(
                name="Role pings",
                value=f"{message.author.mention} ghost pinged {ping_list}in {message.channel.mention}",
                inline=False,
            )

        user_mentions = [member for member in mentions if not member.bot]
        if user_mentions:
            ping_list = ""
            for member in user_mentions:
                ping_list += member.mention + " "
            ghost_ping_embed.add_field(
                name="Member pings",
                value=f"{message.author.mention} ghost pinged {ping_list}in {message.channel.mention}",
                inline=False,
            )

        if len(ghost_ping_embed.fields) > 0:
            mod_logs = self.client.config.mod_logs_channel
            ghost_ping_embed.add_field(
                name="Message content",
                value=message.content if message.content else "No content",
                inline=False,
            )
            ghost_ping_embed.set_footer(text="PESU Bot")
            await mod_logs.send(embed=ghost_ping_embed)

    @commands.Cog.listener()
    async def on_message_edit(self, before: discord.Message, after: discord.Message) -> None:
        if before.author.bot:
            return

        old_mentions = self._filter_reply_mentions(before)
        new_mentions = after.mentions
        old_role_mentions = before.role_mentions
        new_role_mentions = after.role_mentions

        old_mention_ids = {m.id for m in old_mentions}
        new_mention_ids = {m.id for m in new_mentions}
        old_role_ids = {r.id for r in old_role_mentions}
        new_role_ids = {r.id for r in new_role_mentions}

        # Check if there are any mention changes
        has_mention_changes = (
            old_mention_ids != new_mention_ids
            or old_role_ids != new_role_ids
            or before.mention_everyone != after.mention_everyone
        )

        if not has_mention_changes:
            return

        ghost_ping_embed = self._create_ghost_ping_embed("Ghost Ping Alert (Edited Message)")

        self._add_everyone_ping_field(ghost_ping_embed, before)
        self._add_role_ping_fields(ghost_ping_embed, old_role_mentions, before)
        self._add_member_ping_fields(ghost_ping_embed, old_mentions, before)

        if len(ghost_ping_embed.fields) > 0:
            ghost_ping_embed.add_field(name="Jump URL", value=before.jump_url, inline=False)
            mod_logs = self.client.config.mod_logs_channel
            await mod_logs.send(embed=ghost_ping_embed)

    @commands.Cog.listener()
    async def on_thread_create(self, thread: discord.Thread) -> None:
        await thread.join()


async def setup(client: DiscordBot) -> None:
    await client.add_cog(Events(client))
