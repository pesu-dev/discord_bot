"""
Configuration data classes for the Discord bot.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from bot import DiscordBot


class Config:
    """Configuration class."""

    # Role IDs
    ROLES = {
        "FUNCTIONAL": {
            "ADMIN": 742800061280550923,
            "MOD": 742798158966292640,
            "BOT_DEV": 750556082371559485,
            "LINKED": 749683320941445250,
            "JUST_JOINED": 798765678739062804,
            "MUTED": 775981947079491614,
        },
        "BRANCH": {
            "CSE": 984846616580198450,
            "CSE (AI&ML)": 1061350128939716768,
            "ECE": 984846618371174400,
            "EEE": 984846620157964389,
            "ME": 984846621848248320,
            "BT": 984846623676969030,
            "CV": 984846625446985728,
            "B ARCH": 984846627158257684,
            "BBA": 984846628596899881,
            "B.DES": 984846630396235850,
            "BBA LLB": 984846632405315646,
            "BBA-HEM": 984846634385047632,
            "BA LLB": 984846636226314270,
            "BBA - Sports Management": 984846638025670726,
            "BCA": 984846639841820752,
            "B.Com": 984846642354192484,
            "BBA (Hons) in Business Analytics": 1023509952964341820,
            "B.Com (Hons) with ACCA": 1023510367026036826,
            "Psychology": 1023510685705044009,
            "Sports Management": 1023511154649223240,
            "Bachelor of Pharmacy": 1023512100724817940,
            "Nursing": 1061350434675101726,
            "CA": 1086905421291335711,
            "International Accounting and Finance": 1129414449485316176,
            "Business Analytics": 1136371141330608138,
            "MBA": 1289303483522093127,
            "MBBS": 1336785790730108978,
        },
        "YEAR": {
            "2015": 1119203107130318889,
            "2016": 1106834902667759717,
            "2017": 1079825096287453244,
            "2018": 984846644031942697,
            "2019": 984846646271696977,
            "2020": 984846648112971867,
            "2021": 984846649488732161,
            "2022": 1023513091994025994,
            "2023": 1123313984163041410,
            "2024": 1244601965514588170,
            "2025": 1381083961895157813,
        },
        "CAMPUS": {"RR": 984872936529887322, "EC": 984873178339897384},
    }

    # Channel IDs
    CHANNELS = {
        "BOT_LOGS": 786084620944146504,
        "MOD_LOGS": 778678059879890944,
        "NQN_LOGS": 927077979383824484,
        "WELCOME": 742946580285620225,
        "LOBBY": 860224115633160203,
    }

    def __init__(self, bot: DiscordBot) -> None:
        """Initialize with bot instance."""
        self.bot = bot
        self.guild_id = int(os.getenv("GUILD_ID", 742797665301168220))

    @property
    def guild(self) -> discord.Guild:
        """Get the Discord guild object."""
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            msg = f"Guild with ID {self.guild_id} not found"
            raise ValueError(msg)
        return guild

    def get_role(self, category: str, name: str) -> discord.Role:
        """Get role by category and name using discord.py utilities."""
        role_id = self.ROLES.get(category, {}).get(name)
        if role_id is None:
            raise ValueError(f"Role '{name}' not found in category '{category}'")
        role = self.guild.get_role(role_id)
        if role is None:
            raise ValueError(f"Role with ID {role_id} not found")
        return role

    def get_channel(self, name: str) -> discord.TextChannel | discord.Thread:
        """Get channel by name using discord.py utilities."""
        channel_id = self.CHANNELS.get(name)
        if channel_id is None:
            raise ValueError(f"Channel '{name}' not found")
        channel = self.guild.get_channel(channel_id)
        if isinstance(channel, discord.TextChannel | discord.Thread):
            return channel
        raise ValueError(f"Channel with ID {channel_id} not found")

    # Convenience methods for common roles

    @property
    def admin_role(self) -> discord.Role:
        """Get admin role."""
        return self.get_role("FUNCTIONAL", "ADMIN")

    @property
    def mod_role(self) -> discord.Role:
        """Get moderator role."""
        return self.get_role("FUNCTIONAL", "MOD")

    @property
    def bot_dev_role(self) -> discord.Role:
        """Get bot developer role."""
        return self.get_role("FUNCTIONAL", "BOT_DEV")

    @property
    def linked_role(self) -> discord.Role:
        """Get linked role."""
        return self.get_role("FUNCTIONAL", "LINKED")

    @property
    def just_joined_role(self) -> discord.Role:
        """Get just joined role."""
        return self.get_role("FUNCTIONAL", "JUST_JOINED")

    @property
    def muted_role(self) -> discord.Role:
        """Get muted role."""
        return self.get_role("FUNCTIONAL", "MUTED")

    def has_mod_permissions(self, member: discord.Member) -> bool:
        """Check if a member is admin/mod."""
        return any(role in member.roles for role in [self.admin_role, self.mod_role])

    def has_bot_dev_permissions(self, member: discord.Member) -> bool:
        """Check if a member has bot developer permissions."""
        return self.bot_dev_role in member.roles

    # Convenience methods for common channels

    @property
    def bot_logs_channel(self) -> discord.TextChannel | discord.Thread:
        """Get bot logs channel."""
        return self.get_channel("BOT_LOGS")

    @property
    def mod_logs_channel(self) -> discord.TextChannel | discord.Thread:
        """Get mod logs channel."""
        return self.get_channel("MOD_LOGS")

    @property
    def lobby_channel(self) -> discord.TextChannel | discord.Thread:
        """Get lobby channel."""
        return self.get_channel("LOBBY")
