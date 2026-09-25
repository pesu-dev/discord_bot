from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord
from discord import app_commands
from discord.ext import tasks
from discord.ext.commands import Cog
from pymongo.errors import DuplicateKeyError

from src.cogs.mod.anon import AnonModCommands
from src.cogs.mod.commands import ModCommands
from src.cogs.mod.groups import ModGroups
from src.cogs.mod.link import LinkCommands
from src.data.mongo import ServerBan
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

        self.tasks = [self.check_mutes_loop, self.cleanup_stale_records_loop, self.reconcile_pending_bans_loop]
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
                member = await guild.fetch_member(int(mute.discord_user_id))
            except discord.NotFound:
                await self.client.stores.mutes.mark_unmuted(mute.id, unmuted_at=now)
                continue

            muted_role = self.client.config.muted_role
            if muted_role and muted_role in member.roles:
                try:
                    await member.remove_roles(muted_role, reason="Automatic unmute by loop")
                except Exception as e:
                    embed = ug.build_unknown_error_embed(e)
                    bot_logs = self.client.config.bot_logs_channel
                    await bot_logs.send(embed=embed)

            await self.client.stores.mutes.mark_unmuted(mute.id, unmuted_at=now)

            channel = guild.get_channel(mute.discord_channel_id)
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
                await self.client.config.mod_logs_channel.send(
                    embed=ug.build_embed(
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

    @tasks.loop(hours=1)
    async def cleanup_stale_records_loop(self) -> None:
        now = datetime.now(UTC)
        await self.client.stores.mutes.delete_stale(now)
        await self.client.stores.anon_mutes.delete_stale(now)
        await self.client.stores.anon_bans.delete_stale(now)

    @cleanup_stale_records_loop.before_loop
    async def before_cleanup_stale_records_loop(self) -> None:
        await self.client.wait_until_ready()

    @tasks.loop(minutes=5)
    async def reconcile_pending_bans_loop(self) -> None:
        """Converge partial identity operations to the current Discord ban state.

        Pending records are evidence of a failed Mongo step, not commands to
        replay. Checking Discord immediately before the identity mutation makes a
        delayed old ``ban``/``unban`` record harmless after a newer moderator or
        manual Discord decision.
        """
        for record in await self.client.stores.pending_server_bans.list_pending(limit=100):
            if record.id is None:
                continue
            canonical_prn = ug.validate_prn(record.prn)
            if canonical_prn is None:
                self.client.logger.error(
                    "Invalid PRN in pending identity operation %s for user %s; leaving record for repair",
                    record.operation_id,
                    record.discord_user_id,
                )
                await self.client.stores.pending_server_bans.mark_retry_failure(record, "invalid stored PRN")
                continue
            try:
                async with self._identity_operation_lock(record.discord_user_id):
                    try:
                        await self.client.config.guild.fetch_ban(discord.Object(id=int(record.discord_user_id)))
                    except discord.NotFound:
                        discord_banned = False
                    else:
                        discord_banned = True

                    if discord_banned:
                        await self.client.stores.server_bans.insert_one(
                            ServerBan(
                                prn=canonical_prn,
                                discord_user_id=record.discord_user_id,
                                reason=record.reason,
                                banned_at=datetime.now(UTC),
                            )
                        )
                    else:
                        await self.client.stores.server_bans.remove_ban_for_user(canonical_prn, record.discord_user_id)
            except DuplicateKeyError:
                pass
            except Exception:
                self.client.logger.error(
                    "Reconciling pending identity operation %s for PRN %s failed",
                    record.operation_id,
                    canonical_prn,
                    exc_info=True,
                )
                await self.client.stores.pending_server_bans.mark_retry_failure(record, "reconciliation failed")
                continue
            await self.client.stores.pending_server_bans.delete_if_current(record)

    @reconcile_pending_bans_loop.before_loop
    async def before_reconcile_pending_bans_loop(self) -> None:
        await self.client.wait_until_ready()


async def setup(client: DiscordBot) -> None:
    cog = SlashMod(client)
    await client.add_cog(cog, guild=client.config.guild_object)
    client.tree.add_command(
        cog.ctx_menu,
        guild=client.config.guild_object,
    )
