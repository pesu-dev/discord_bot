from __future__ import annotations

from datetime import datetime

import discord


class EventHelpers:
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
