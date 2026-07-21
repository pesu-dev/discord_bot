from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import discord

from src.utils import general as ug

if TYPE_CHECKING:
    from src.bot import DiscordBot


class ModHelpers:
    client: DiscordBot

    async def _send_mod_log(self, embed: discord.Embed) -> None:
        """Send an embed to the configured mod logs channel."""
        await self.client.config.mod_logs_channel.send(embed=embed)

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
        for user_id, messages in self.client.anon_cache.items():
            for message in messages:
                if str(message_id) == message["message_id"]:
                    return guild.get_member(int(user_id))
        return None

    async def _handle_ban_message_link(self, interaction: discord.Interaction, link: str) -> discord.Member | None:
        """Handle message link validation and user lookup."""
        if interaction.guild is None or interaction.channel is None:
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
        banned_at = datetime.now(UTC)

        if time_str is not None:
            seconds = ug.parse_time(time_str)
            expires_at = banned_at + timedelta(seconds=seconds)
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
        return "Permanent" if expires_at is None else discord.utils.format_dt(expires_at, "R")

    async def _apply_anon_ban(
        self,
        interaction: discord.Interaction,
        user_to_ban: discord.Member,
        *,
        time: str | None,
        reason: str | None,
        message_link: str | None = None,
    ) -> None:
        if await self._check_user_anon_ban(str(user_to_ban.id)):
            await interaction.followup.send(content="Dude's already banned from anon messaging", ephemeral=True)
            return

        if time is not None and await self._validate_and_parse_time(interaction, time) is None:
            return

        ban_reason = reason if reason is not None else "No reason provided"
        expiry_timestamp = await self._create_and_store_ban(str(user_to_ban.id), ban_reason, time)

        if expiry_timestamp == "Permanent":
            confirmation_msg = (
                f"Member has been banned from anon messaging, their ban will never expire\nReason: {ban_reason}"
            )
        else:
            confirmation_msg = (
                f"Member has been banned from anon messaging, their ban will expire {expiry_timestamp}\n"
                f"Reason: {ban_reason}"
            )

        await interaction.followup.send(content=confirmation_msg)

        ban_fields: list[dict] = [
            {"name": "Reason", "value": ban_reason},
            {"name": "Expires", "value": expiry_timestamp},
        ]
        if message_link is not None:
            ban_fields.insert(
                1,
                {"name": "Message Link", "value": f"[Click here to view the message]({message_link})"},
            )

        ban_embed = ug.build_embed(
            title="Notification",
            description="You have been banned from using anon messaging",
            color=discord.Color.red(),
            fields=ban_fields,
        )

        if not await ug.send_dm_safely(user_to_ban, ban_embed):
            await interaction.followup.send(content="DMs were closed", ephemeral=True)
