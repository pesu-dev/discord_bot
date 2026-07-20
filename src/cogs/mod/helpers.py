from __future__ import annotations

from datetime import UTC, datetime
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from src.bot import DiscordBot


class ModHelpers:
    client: DiscordBot

    async def _send_mod_log(self, embed: discord.Embed) -> None:
        """Send an embed to the configured mod logs channel."""
        await self.client.config.mod_logs_channel.send(embed=embed)

    @staticmethod
    def _build_unmute_embed(member: discord.Member) -> discord.Embed:
        """Public-facing unmute embed shown in the channel."""
        embed = discord.Embed(title="Unmute", color=discord.Color.green(), timestamp=datetime.now(UTC))
        embed.set_footer(text="PESU Bot")
        embed.add_field(name="Unmuted user", value=f"{member.mention} welcome back", inline=False)
        return embed

    @staticmethod
    def _build_unmute_logs_embed(member: discord.Member, moderator_mention: str) -> discord.Embed:
        """Mod-log unmute embed recording who performed the unmute."""
        embed = discord.Embed(title="Unmute", color=discord.Color.green(), timestamp=datetime.now(UTC))
        embed.set_footer(text="PESU Bot")
        embed.add_field(
            name="Unmuted user",
            value=f"{member.mention}\nModerator: {moderator_mention}",
            inline=False,
        )
        return embed
