from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING

import discord

from src.data.mongo import AnonBan, AnonMute
from src.utils import general as ug

if TYPE_CHECKING:
    from src.bot import DiscordBot


class ModHelpers:
    client: DiscordBot

    async def _validate_and_parse_time(self, interaction: discord.Interaction, time_str: str) -> int | None:
        """Validate and parse time string, return seconds or None if invalid."""
        try:
            seconds = ug.parse_time(time_str)
            if seconds <= 10:
                await interaction.followup.send(
                    content="You can't mute someone for less than 10 seconds", ephemeral=True
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

    async def _handle_anon_message_link(self, interaction: discord.Interaction, link: str) -> discord.Member | None:
        """Resolve an anon message link to the member who sent it."""
        if interaction.guild is None or interaction.channel is None:
            return None

        try:
            msg = await interaction.channel.fetch_message(int(link.split("/")[-1]))
        except (discord.NotFound, discord.Forbidden, discord.HTTPException):
            await interaction.followup.send(content="Could not find the message", ephemeral=True)
            return None

        member = self._find_user_from_message(str(msg.id), interaction.guild)
        if not member:
            await interaction.followup.send(
                content="This wasn't an anon message only da what you doing?", ephemeral=True
            )
            return None

        return member

    async def _create_and_store_ban(self, discord_user_id: str, reason: str) -> None:
        """Create a permanent anon ban and store it."""
        ban = AnonBan(
            discord_user_id=discord_user_id,
            reason=reason,
            banned_at=datetime.now(UTC),
        )
        await self.client.stores.anon_bans.insert_one(ban)

    async def _create_and_store_anon_mute(
        self,
        discord_user_id: str,
        moderator_discord_user_id: str,
        reason: str,
        seconds: int,
    ) -> datetime:
        """Create an anon mute and store it. Returns the scheduled unmute time."""
        muted_at = datetime.now(UTC)
        original_unmute_time = muted_at + timedelta(seconds=seconds)
        mute = AnonMute(
            discord_user_id=discord_user_id,
            moderator_discord_user_id=moderator_discord_user_id,
            muted_at=muted_at,
            original_unmute_time=original_unmute_time,
            reason=reason,
        )
        await self.client.stores.anon_mutes.insert_one(mute)
        return original_unmute_time

    async def _apply_anon_ban(
        self,
        interaction: discord.Interaction,
        user_to_ban: discord.Member,
        *,
        reason: str | None,
        message_link: str | None = None,
    ) -> None:
        user_id = str(user_to_ban.id)
        if await self.client.stores.anon_bans.has_active(user_id):
            await interaction.followup.send(content="Dude's already banned from anon messaging", ephemeral=True)
            return

        ban_reason = reason if reason is not None else "No reason provided"
        await self._create_and_store_ban(user_id, ban_reason)

        confirmation_msg = (
            f"Member has been banned from anon messaging, their ban will never expire\nReason: {ban_reason}"
        )
        await interaction.followup.send(content=confirmation_msg)

        ban_fields: list[dict] = [
            {"name": "Reason", "value": ban_reason},
            {"name": "Expires", "value": "Permanent"},
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

    async def _apply_anon_mute(
        self,
        interaction: discord.Interaction,
        user_to_mute: discord.Member,
        *,
        time: str,
        reason: str,
        message_link: str | None = None,
    ) -> None:
        user_id = str(user_to_mute.id)
        if await self.client.stores.anon_bans.has_active(user_id):
            await interaction.followup.send(
                content="Dude is already permanently banned from anon messaging",
                ephemeral=True,
            )
            return
        if await self.client.stores.anon_mutes.has_active(user_id):
            await interaction.followup.send(content="Dude's already muted from anon messaging", ephemeral=True)
            return

        seconds = await self._validate_and_parse_time(interaction, time)
        if seconds is None:
            return

        original_unmute_time = await self._create_and_store_anon_mute(
            user_id,
            str(interaction.user.id),
            reason,
            seconds,
        )
        expiry = discord.utils.format_dt(original_unmute_time, "R")
        await interaction.followup.send(
            content=f"Member has been muted from anon messaging until {expiry}\nReason: {reason}"
        )

        mute_fields: list[dict] = [
            {"name": "Reason", "value": reason},
            {"name": "Expires", "value": expiry},
        ]
        if message_link is not None:
            mute_fields.insert(
                1,
                {"name": "Message Link", "value": f"[Click here to view the message]({message_link})"},
            )

        mute_embed = ug.build_embed(
            title="Notification",
            description="You have been muted from using anon messaging",
            color=discord.Color.red(),
            fields=mute_fields,
        )
        if not await ug.send_dm_safely(user_to_mute, mute_embed):
            await interaction.followup.send(content="DMs were closed", ephemeral=True)
