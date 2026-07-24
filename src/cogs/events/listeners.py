from __future__ import annotations

import asyncio
import os
import random
import re
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from src.cogs.events.helpers import EventHelpers
from src.utils.general import build_embed

if TYPE_CHECKING:
    from src.bot import DiscordBot


class EventListeners(EventHelpers):
    client: DiscordBot

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member) -> None:
        bot_logs = self.client.config.bot_logs_channel
        just_joined = self.client.config.just_joined_role
        await bot_logs.send(f"{member.mention} Joined!!")

        link_record = await self.client.stores.links.find_one(user_id=str(member.id))
        roles_to_add = [just_joined]
        should_delete_link = bool(link_record and not link_record.linked_at)

        if link_record and link_record.linked_at and link_record.prn:
            student_record = await self.client.stores.students.find_one(prn=link_record.prn)
            if student_record:
                roles_to_add = []
                for value in (
                    student_record.year,
                    student_record.branch.short,
                    student_record.campus.short,
                ):
                    if not value:
                        continue
                    try:
                        roles_to_add.append(self.client.config.resolve_academic_role(value))
                    except ValueError:
                        continue
                if len(roles_to_add) == 3:
                    roles_to_add.append(self.client.config.linked_role)
                else:
                    roles_to_add = [just_joined]
                    should_delete_link = True
            else:
                should_delete_link = True

        await member.add_roles(*roles_to_add)
        if should_delete_link and link_record and link_record.id is not None:
            await self.client.stores.links.delete_one(id=link_record.id)

    @commands.Cog.listener()
    async def on_member_remove(self, member: discord.Member) -> None:
        bot_logs = self.client.config.bot_logs_channel
        await bot_logs.send(f"{member.mention} Left!!")

        link_record = await self.client.stores.links.find_one(user_id=str(member.id))

        if link_record and link_record.linked_at is None and link_record.id is not None:
            await self.client.stores.links.delete_one(id=link_record.id)
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

        ghost_ping_embed = build_embed(title="Ghost Ping Alert", color=discord.Color.blue())
        self._add_everyone_ping_field(ghost_ping_embed, message)
        self._add_role_ping_fields(ghost_ping_embed, message.role_mentions, message)
        self._add_member_ping_fields(ghost_ping_embed, message.mentions, message)

        if len(ghost_ping_embed.fields) > 0:
            ghost_ping_embed.add_field(
                name="Message content",
                value=message.content if message.content else "No content",
                inline=False,
            )
            mod_logs = self.client.config.mod_logs_channel
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

        ghost_ping_embed = build_embed(title="Ghost Ping Alert (Edited Message)", color=discord.Color.blue())

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
