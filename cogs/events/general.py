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
        """
        Thin wrapper listener that delegates real work to helper methods to keep complexity low.
        """
        # If it's an anon bot message from any bot that's not us, only process if it's an anon message.
        if message.author.bot and message.author.id != self.client.user.id:
            if not (message.embeds and message.embeds[0].title == "Anon Message"):
                return
            # if it is an anon message (bot message with embed), fall through — other handlers may act on it
            # (original logic only continued when it was an anon message)
            return

        # Try to handle reply-to-anon flows (separate helper to reduce complexity)
        if message.reference and message.reference.message_id:
            try:
                await self._process_reply_to_anon(message)
            except (discord.NotFound, discord.Forbidden, discord.HTTPException):
                # Could not fetch the replied message or other discord errors — ignore as before
                pass

        # Handle EC Campus keyword check separately
        try:
            await self._maybe_handle_ec_campus_keyword(message)
        except Exception:
            # Don't let a non-critical error here bubble up and break other things
            pass

        # End of on_message
        return

    async def _process_reply_to_anon(self, message: discord.Message) -> None:
        """
        Handle replies to anon messages and DM the original anon sender if appropriate.
        This is extracted from on_message to reduce the complexity of the listener.
        """
        replied_message = await message.channel.fetch_message(message.reference.message_id)
        if not self._is_anon_message(replied_message):
            return

        anon_cog = self.client.get_cog("SlashAnon")
        if not anon_cog or not hasattr(anon_cog, "anon_cache"):
            return

        original_sender_id = self._find_sender_id(anon_cog, replied_message.id)
        current_sender_id, is_current_anon = await self._identify_current_sender(anon_cog, message)

        if not (original_sender_id and current_sender_id and original_sender_id != current_sender_id):
            return

        await self._notify_original_sender(original_sender_id, current_sender_id, message, is_current_anon)

    # ---------- helpers for _process_reply_to_anon ----------

    @staticmethod
    def _is_anon_message(msg: discord.Message) -> bool:
        return msg.author.bot and msg.embeds and msg.embeds[0].title == "Anon Message"

    @staticmethod
    def _find_sender_id(anon_cog: commands.Cog, target_message_id: int | str) -> str | None:
        for user_id, messages in anon_cog.anon_cache.items():
            if any(str(target_message_id) == msg["message_id"] for msg in messages):
                return user_id
        return None

    async def _identify_current_sender(
        self, anon_cog: commands.Cog, message: discord.Message
    ) -> tuple[str | None, bool]:
        """Return (sender_id, is_current_anon)."""
        is_current_anon = self._is_anon_message(message) and message.author == self.client.user
        if is_current_anon:
            for user_id, messages in anon_cog.anon_cache.items():
                if any(str(message.id) == msg["message_id"] for msg in messages):
                    return user_id, True
            return None, True
        return str(message.author.id), False

    async def _notify_original_sender(
        self,
        original_sender_id: str,
        current_sender_id: str,
        message: discord.Message,
        is_current_anon: bool,
    ) -> None:
        """Build embed, button, and DM the original anon sender."""
        try:
            original_sender = await self.client.fetch_user(int(original_sender_id))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            return
        if not original_sender:
            return

        link_record = await self.client.link_collection.find_one({"userId": str(original_sender.id)})
        if link_record and link_record.get("anon_notifications", True) is False:
            return

        reply_type = "anon user" if is_current_anon else message.author.display_name

        embed = discord.Embed(
            title="Reply to Your Anon Message",
            description=f"An {reply_type} replied to your anon message"
            if is_current_anon
            else f"{reply_type} replied to your anon message",
            color=discord.Color.blue(),
        )
        embed.add_field(
            name="Jump to Reply",
            value=f"[Click here to view the reply]({message.jump_url})",
            inline=False,
        )
        embed.set_footer(text="PESU Bot")
        embed.timestamp = discord.utils.utcnow()

        is_subscribed = link_record.get("anon_notifications", True) if link_record else True
        view = self._make_toggle_view(original_sender.id, is_subscribed)

        try:
            await original_sender.send(embed=embed, view=view)
        except (discord.Forbidden, discord.HTTPException, discord.NotFound):
            pass

    def _make_toggle_view(self, user_id: int, is_subscribed: bool) -> discord.ui.View:
        """Create the subscribe/unsubscribe button view."""
        view = discord.ui.View()
        toggle_button = discord.ui.Button(
            label="Unsubscribe from notifications" if is_subscribed else "Subscribe to notifications",
            style=discord.ButtonStyle.secondary if is_subscribed else discord.ButtonStyle.primary,
            custom_id=f"toggle_anon_notifications_{user_id}",
        )

        async def toggle_callback(interaction: discord.Interaction) -> None:
            if interaction.user.id != user_id:
                await interaction.response.send_message("You can't toggle someone else's subscription.", ephemeral=True)
                return

            current_record = await self.client.link_collection.find_one({"userId": str(user_id)})
            currently_subscribed = current_record.get("anon_notifications", True) if current_record else True

            new_status = not currently_subscribed
            await self.client.link_collection.update_one(
                {"userId": str(user_id)},
                {"$set": {"anon_notifications": new_status}},
                upsert=True,
            )

            if new_status:
                await interaction.response.send_message(
                    "✅ You have been subscribed to anon reply notifications.", ephemeral=True
                )
            else:
                await interaction.response.send_message(
                    "❌ You have been unsubscribed from anon reply notifications.", ephemeral=True
                )

        toggle_button.callback = toggle_callback
        view.add_item(toggle_button)
        return view

    async def _maybe_handle_ec_campus_keyword(self, message: discord.Message) -> None:
        """
        Handle the EC Campus keyword check (20% random chance in prod) extracted out to reduce complexity.
        """
        if os.getenv("APP_ENV") != "prod":
            return

        if random.random() > 0.2:
            return

        # Only check text content
        content = (message.content or "").lower()
        if not content:
            return

        patterns = [r"\becc\b", r"\bec campus\b", r"\bec\b"]
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
