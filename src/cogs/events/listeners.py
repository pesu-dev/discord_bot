from __future__ import annotations

import asyncio
import os
import random
import re
from datetime import timedelta
from typing import TYPE_CHECKING

import discord
from discord.ext import commands

from src.cogs.events.helpers import EventHelpers
from src.utils import general as ug
from src.utils.general import build_embed

if TYPE_CHECKING:
    from src.bot import DiscordBot


class EventListeners(EventHelpers):
    client: DiscordBot
    HONEYPOT_ACTION = "kick"  # allowed: kick | ban | timeout

    def _build_fafo_banner(self) -> discord.Embed:
        return build_embed(
            title="DO NOT SEND MESSAGES IN THIS CHANNEL",
            description=(
                "This channel is used to catch spam bots. Any messages sent here will result in a **timeout and kick**."
            ),
            color=discord.Color.red(),
            thumbnail="https://cdn.jsdelivr.net/gh/twitter/twemoji@14.0.2/assets/72x72/1f36f.png",
        )

    @staticmethod
    def _build_fafo_view(count: int) -> discord.ui.View:
        view = discord.ui.View(timeout=None)
        view.add_item(
            discord.ui.Button(
                style=discord.ButtonStyle.secondary,
                label=f"🍯 Timeouts & Kicks: {count}",
                disabled=True,
            )
        )
        return view

    async def _ensure_fafo_banner(self) -> discord.Message:
        async with self._fafo_lock:
            channel = self.client.config.honeypot_channel

            if self._fafo_message_id is not None:
                try:
                    return await channel.fetch_message(self._fafo_message_id)
                except discord.NotFound:
                    self._fafo_message_id = None

            # Find the existing banner after a bot restart.
            async for message in channel.pins(limit=None):
                if (
                    message.author.id == self.client.user.id
                    and message.embeds
                    and message.embeds[0].title == "DO NOT SEND MESSAGES IN THIS CHANNEL"
                ):
                    self._fafo_message_id = message.id
                    return message

            # Create the banner only when it does not already exist.
            count = 0
            banner = await channel.send(
                embed=self._build_fafo_banner(),
                view=self._build_fafo_view(count),
            )
            await banner.pin(reason="FAFO honeypot banner")
            self._fafo_message_id = banner.id
            return banner

    async def _update_fafo_banner(self) -> None:
        banner = await self._ensure_fafo_banner()

        # pre compute the count from the button label
        count = 0
        if banner.components:
            row = banner.components[0]
            if hasattr(row, "children") and row.children:
                button = row.children[0]
                if hasattr(button, "label") and button.label:
                    match = re.search(r"\d+", button.label)
                    if match:
                        count = int(match.group(0))

        count += 1
        view = self._build_fafo_view(count)
        await banner.edit(embed=self._build_fafo_banner(), view=view)

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

    async def _apply_honeypot_action(self, member: discord.Member, source_message: discord.Message) -> str:
        reason = f"Honeypot trap in #{source_message.channel} ({source_message.channel.id})"
        dm_embed = build_embed(
            title="You have been removed",
            color=discord.Color.red(),
            description=f"You were removed from **{member.guild.name}** for triggering the honeypot channel.",
        )
        await ug.send_dm_safely(member, embed=dm_embed)

        if self.HONEYPOT_ACTION == "ban":
            await member.ban(delete_message_days=0, reason=reason)
            return "Banned"

        until = discord.utils.utcnow() + timedelta(hours=24)
        await member.timeout(until, reason=reason)

        await member.kick(reason=reason)
        return "Timed out & Kicked"

    @commands.Cog.listener()
    async def on_message(self, message: discord.Message) -> None:
        if message.author.bot:
            return

        # Honeypot detection and action
        if message.channel.id == self.client.config.honeypot_channel.id and isinstance(message.author, discord.Member):
            try:
                await message.delete()
            except (discord.Forbidden, discord.NotFound):
                pass

            # Keep existing moderation guardrails (admin/mod/bots protected)
            target_error = ug.mod_target_error(message.author, self.client.config)
            if target_error is not None:
                await self.client.config.mod_logs_channel.send(
                    f"Honeypot triggered by protected user {message.author.mention}; skipped auto-action. "
                    f"Reason: {target_error}"
                )
                return

            try:
                action_text = await self._apply_honeypot_action(message.author, message)
                await self._update_fafo_banner()

                trap_embed = build_embed(
                    title="Honeypot Triggered",
                    color=discord.Color.red(),
                    timestamp=discord.utils.utcnow(),
                    description=f"{message.author.mention} got trapped in {message.channel.mention}",
                    fields=[
                        {"name": "Action", "value": action_text, "inline": True},
                        {
                            "name": "Message",
                            "value": message.content if message.content else "*No content*",
                            "inline": False,
                        },
                    ],
                )
                await self.client.config.mod_logs_channel.send(embed=trap_embed)

            except discord.Forbidden:
                await self.client.config.mod_logs_channel.send(
                    f"Failed honeypot action for {message.author.mention}: "
                    "missing permissions/role hierarchy "
                    "(kick/ban/timeout and/or FAFO banner update)."
                )
            except discord.HTTPException as exc:
                await self.client.config.mod_logs_channel.send(
                    f"Failed honeypot action for {message.author.mention}: {exc}"
                )
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
