from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import TYPE_CHECKING

import discord
from bson.errors import InvalidId
from pymongo.errors import DuplicateKeyError

from src.data.mongo import AnonBan, AnonMute, PendingServerBan, ServerBan
from src.utils import general as ug

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from src.bot import DiscordBot

logger = logging.getLogger(__name__)


class IdentityBanResult(StrEnum):
    """Outcome of recording a PRN identity ban after a Discord ban."""

    RECORDED = "recorded"
    ALREADY_RECORDED = "already_recorded"
    NO_IDENTITY = "no_identity"
    PERSISTENCE_FAILED = "persistence_failed"
    REMOVED = "removed"
    REMOVE_FAILED = "remove_failed"


class ModHelpers:
    client: DiscordBot

    @asynccontextmanager
    async def _identity_operation_lock(self, discord_user_id: str) -> AsyncIterator[None]:
        """Serialize identity reconciliation with bot-originated moderation actions."""
        locks = getattr(self.client, "identity_operation_locks", None)
        if locks is None:
            locks = {}
            self.client.identity_operation_locks = locks
        lock = locks.setdefault(discord_user_id, asyncio.Lock())
        async with lock:
            yield

    async def _validate_ban_args(self, interaction: discord.Interaction, reason: str, delete_message_days: int) -> bool:
        """Validate `/ban` options, reporting failures ephemerally. Returns True when valid."""
        if not 1 <= len(reason) <= 400:
            await interaction.followup.send(
                content="Reason must be between 1 and 400 characters",
                ephemeral=True,
            )
            return False
        if delete_message_days < 0 or delete_message_days > 7:
            await interaction.followup.send(
                content="Delete message days must be between 0 and 7",
                ephemeral=True,
            )
            return False
        return True

    async def _lookup_server_ban_prn(self, user: discord.User) -> tuple[str | None, bool]:
        """Return ``(prn, malformed)`` for a ban target.

        The PRN comes exclusively from the bot's existing verified ``links`` record.
        ``(None, False)`` means no link exists; ``(None, True)`` means a links row
        exists but has no usable PRN (legacy/corrupt data) and the ban must fail closed.
        Only narrow deserialization errors map to malformed; database errors and
        unexpected exceptions propagate so the ban aborts loudly.
        """
        discord_id = str(user.id)
        try:
            link = await self.client.stores.links.find_one(discord_user_id=discord_id)
        except (KeyError, TypeError, ValueError, InvalidId) as exc:
            logger.warning("Malformed links record for user %s during /ban: %s", user.id, exc)
            return None, True
        if link is None:
            return None, False
        canonical = ug.validate_prn(link.prn)
        if canonical is None:
            logger.warning("Links record for user %s has no usable PRN during identity check", user.id)
            return None, True
        return canonical, False

    async def _lookup_unban_prn(self, user: discord.User) -> tuple[str | None, bool]:
        """Resolve an identity ban for unban, preferring its durable audit record.

        A link can be removed after a ban, but ``server_bans`` is deliberately
        retained. Only fall back to ``links`` when no identity-ban record exists.
        """
        try:
            identity_ban = await self.client.stores.server_bans.find_one(discord_user_id=str(user.id))
        except (KeyError, TypeError, ValueError, InvalidId) as exc:
            logger.warning("Malformed server_bans record for user %s during /unban: %s", user.id, exc)
            return None, True
        if identity_ban is not None:
            canonical = ug.validate_prn(identity_ban.prn)
            if canonical is None:
                logger.error("Invalid PRN in server_bans record for user %s; refusing removal", user.id)
                return None, True
            return canonical, False
        return await self._lookup_server_ban_prn(user)

    async def _persist_server_ban_identity(
        self,
        user: discord.User,
        prn: str | None,
        reason: str,
    ) -> tuple[IdentityBanResult, str | None]:
        """Persist a PRN identity ban after a successful Discord ban.

        Must only run after ``guild.ban`` succeeds, so a failed Discord ban never
        leaves a false identity ban. There is deliberately no read-before-write:
        the unique PRN index is the single atomic guard, so concurrent and repeated
        bans converge on one record via ``DuplicateKeyError``. Never raises for
        persistence failures; the caller renders exactly one authoritative response
        from the returned outcome.
        """
        if prn is None:
            return IdentityBanResult.NO_IDENTITY, None
        try:
            await self.client.stores.server_bans.insert_one(
                ServerBan(
                    prn=prn,
                    discord_user_id=str(user.id),
                    reason=reason,
                    banned_at=datetime.now(UTC),
                )
            )
        except DuplicateKeyError:
            logger.info("Server ban identity for PRN %s already recorded", prn)
            await self._clear_pending_identity_op(user)
            return IdentityBanResult.ALREADY_RECORDED, prn
        except Exception:
            logger.error(
                "Failed to persist server ban identity: prn=%s discord_user_id=%s reason=%s",
                prn,
                user.id,
                reason,
                exc_info=True,
            )
            await self._record_pending_identity_op(
                op="ban", user=user, prn=prn, reason=reason, detail="insert into server_bans failed"
            )
            return IdentityBanResult.PERSISTENCE_FAILED, prn
        await self._clear_pending_identity_op(user)
        return IdentityBanResult.RECORDED, prn

    async def _ban_with_identity(
        self,
        interaction: discord.Interaction,
        user: discord.User,
        prn: str | None,
        reason: str,
        delete_message_days: int,
    ) -> tuple[IdentityBanResult, str | None]:
        """Apply Discord and identity bans as one serialized bot operation."""
        async with self._identity_operation_lock(str(user.id)):
            await interaction.guild.ban(
                user,
                reason=f"Banned by {interaction.user} | {reason}",
                delete_message_seconds=delete_message_days * 86400,
            )
            return await self._persist_server_ban_identity(user, prn, reason)

    async def _remove_server_ban_identity(
        self, user: discord.User, prn: str | None
    ) -> tuple[IdentityBanResult, str | None]:
        """Remove a PRN identity ban after a successful Discord unban. Idempotent.

        Must only run after ``guild.unban`` succeeds for a previously banned user.
        Never raises for removal failures; the caller renders exactly one
        authoritative response from the returned outcome.
        """
        if prn is None:
            return IdentityBanResult.NO_IDENTITY, None
        try:
            removed = await self.client.stores.server_bans.remove_ban_for_user(prn, str(user.id))
        except Exception:
            logger.error(
                "Failed to remove server ban identity: prn=%s discord_user_id=%s",
                prn,
                user.id,
                exc_info=True,
            )
            await self._record_pending_identity_op(
                op="unban", user=user, prn=prn, reason="", detail="delete from server_bans failed"
            )
            return IdentityBanResult.REMOVE_FAILED, prn
        await self._clear_pending_identity_op(user)
        if not removed:
            return IdentityBanResult.NO_IDENTITY, prn
        return IdentityBanResult.REMOVED, prn

    async def _unban_with_identity(
        self, interaction: discord.Interaction, user: discord.User, reason: str
    ) -> tuple[bool, IdentityBanResult, str | None, bool]:
        """Apply Discord and identity unbans as one serialized bot operation."""
        async with self._identity_operation_lock(str(user.id)):
            try:
                await interaction.guild.fetch_ban(user)
            except discord.NotFound:
                discord_banned = False
            else:
                discord_banned = True

            ban_prn, link_malformed = await self._lookup_unban_prn(user)
            if discord_banned:
                await interaction.guild.unban(user, reason=f"Unbanned by {interaction.user} | {reason}")

            if link_malformed:
                outcome, identity_prn = IdentityBanResult.NO_IDENTITY, None
            else:
                outcome, identity_prn = await self._remove_server_ban_identity(user, ban_prn)
        return discord_banned, outcome, identity_prn, link_malformed

    async def _record_pending_identity_op(
        self, *, op: str, user: discord.User, prn: str, reason: str, detail: str
    ) -> None:
        """Best-effort durable record of an identity op needing reconciliation. Never raises."""
        try:
            await self.client.stores.pending_server_bans.replace_current(
                PendingServerBan(
                    op=op,
                    prn=prn,
                    discord_user_id=str(user.id),
                    reason=reason,
                    failed_at=datetime.now(UTC),
                )
            )
        except Exception:
            logger.error("Failed to record pending identity %s for PRN %s (%s)", op, prn, detail, exc_info=True)

    async def _clear_pending_identity_op(self, user: discord.User) -> None:
        """Best-effort cleanup; state-aware reconciliation remains safe if it fails."""
        try:
            await self.client.stores.pending_server_bans.delete_one(discord_user_id=str(user.id))
        except Exception:
            logger.warning("Failed to clear pending identity operation for user %s", user.id, exc_info=True)

    @staticmethod
    def _ban_result_description(
        *,
        user_mention: str,
        moderator_mention: str,
        reason: str,
        outcome: IdentityBanResult,
        identity_prn: str | None,
    ) -> str:
        """Render the single authoritative moderator response for a completed Discord ban."""
        header = f"{user_mention} was banned by {moderator_mention}\n**Reason:** {reason}"
        if outcome is IdentityBanResult.PERSISTENCE_FAILED:
            return (
                f"{header}\n"
                f"⚠️ **PRN identity ban: FAILED to persist** (`{identity_prn}`). This account may NOT "
                "be protected against ban evasion. Manual recovery required — ask a bot dev to record "
                "the PRN, or remove the Discord ban via Server Settings and re-run `/ban`."
            )
        identity_line = (
            f"\n**PRN identity ban:** `{identity_prn}`" if identity_prn else "\n**PRN identity ban:** none recorded"
        )
        return f"{header}{identity_line}"

    @staticmethod
    def _unban_result_description(
        *,
        user_mention: str,
        moderator_mention: str,
        reason: str,
        discord_unbanned: bool,
        outcome: IdentityBanResult,
        identity_prn: str | None,
        link_malformed: bool,
    ) -> str:
        """Render the single authoritative moderator response for a completed Discord unban."""
        header = f"{user_mention} was unbanned by {moderator_mention}\n**Reason:** {reason}"
        if not discord_unbanned:
            header = f"{user_mention} was not Discord-banned\n**Reason:** {reason}"
        if link_malformed:
            return (
                f"{header}\n"
                "⚠️ **PRN identity ban: UNKNOWN** — the user's link record is malformed, so the "
                "identity state could not be verified. Ask a bot dev to inspect the `links` record."
            )
        if outcome is IdentityBanResult.REMOVE_FAILED:
            return (
                f"{header}\n"
                f"⚠️ **PRN identity ban: FAILED to remove** (`{identity_prn}`). The PRN may still "
                "be blocked from linking. Manual recovery required — ask a bot dev to remove it, "
                "or re-run `/unban` (safe to retry)."
            )
        if outcome is IdentityBanResult.REMOVED:
            return f"{header}\n**PRN identity ban:** removed (`{identity_prn}`)"
        return f"{header}\n**PRN identity ban:** none present"

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
