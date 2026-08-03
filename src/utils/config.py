"""
Configuration data classes for the Discord bot.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import discord

if TYPE_CHECKING:
    from src.bot import DiscordBot


class Config:
    """Configuration class."""

    # The bot only ever runs on a single guild, so this is a constant.
    GUILD_ID = 1368604371323064421

    # Per-environment settings keyed by APP_ENV. All share one cluster for now.
    ENVIRONMENTS = {
        "prod": {"prefix": "!", "db_name": "pesu_v2"},
        "dev": {"prefix": "$", "db_name": "pesu_v2"},
        "local": {"prefix": "?", "db_name": "pesu_v2"},
    }

    ROLES = {
        "ADMIN": 1387103854381760553,
        "MOD": 1387103950099972268,
        "JUNIOR_MOD": 1386828569099112629,
        "BOT_DEV": 1386724072074772610,
        "LINKED": 749683320941445250,
        "JUST_JOINED": 1389256789513470042,
        "MUTED": 1386947661084495913,
    }

    # Guild academic roles use this color (#818689).
    ACADEMIC_ROLE_COLOR = 0x818689

    # PESU full branch name -> Guild role short name.
    BRANCH_SHORT_CODES = {
        "Computer Science and Engineering": "CSE",
        "Computer Science and Engineering (AI&ML)": "CSE (AI&ML)",
        "Electronics and Communication Engineering": "ECE",
        "Mechanical Engineering": "ME",
        "Electrical and Electronics Engineering": "EEE",
        "Civil Engineering": "CV",
        "Biotechnology": "BT",
        "Bachelor of Computer Applications": "BCA",
        "Bachelor of Commerce": "B.Com",
        "Bachelor of Business Administration": "BBA",
        "-Bachelor of Business Administration": "BBA",
        "Master of Business Administration": "MBA",
        "Master of Computer Applications": "MCA",
        "Bachelor of Design": "B.DES",
    }

    # PESU Academy auth service (used by /link).
    PESU_AUTH_URL = "https://pesu-auth.onrender.com/authenticate"

    # Channel IDs
    CHANNELS = {
        "BOT_LOGS": 1393255742802231479,
        "MOD_LOGS": 1386770381733630012,
        "NQN_LOGS": 927077979383824484,
        "WELCOME": 742946580285620225,
        "LOBBY": 860224115633160203,
        "VERIFICATION_LOGS": 1100722146956820510,
        "ERROR_LOGS": 1129317221848596490,
        "HONEYPOT": 1527378274328776864,
    }

    @staticmethod
    def resolve_env() -> tuple[str, str, str]:
        """Resolve (env, prefix, db_name) from APP_ENV. Fails fast on invalid values."""
        env = os.getenv("APP_ENV")
        if env not in Config.ENVIRONMENTS:
            valid = ", ".join(Config.ENVIRONMENTS)
            raise ValueError(f"APP_ENV must be one of [{valid}], got {env!r}")
        settings = Config.ENVIRONMENTS[env]
        return env, settings["prefix"], settings["db_name"]

    def __init__(self, bot: DiscordBot, *, env: str, db_name: str) -> None:
        """Initialize with bot instance and resolved environment settings."""
        self.bot = bot
        self.guild_id = self.GUILD_ID
        self.env = env
        self.db_name = db_name

    @property
    def guild(self) -> discord.Guild:
        """Get the Discord guild object (requires the guild cache to be populated)."""
        guild = self.bot.get_guild(self.guild_id)
        if guild is None:
            msg = f"Guild with ID {self.guild_id} not found"
            raise ValueError(msg)
        return guild

    @property
    def guild_object(self) -> discord.Object:
        """Lightweight guild reference for command registration (no cache needed)."""
        return discord.Object(id=self.guild_id)

    def get_role(self, name: str) -> discord.Role:
        """Get a functional role by name using its configured Discord role ID."""
        role_id = self.ROLES.get(name)
        if role_id is None:
            raise ValueError(f"Role '{name}' not found")
        role = self.guild.get_role(role_id)
        if role is None:
            raise ValueError(f"Role with ID {role_id} not found")
        return role

    def resolve_academic_role(self, name: str) -> discord.Role:
        """Resolve an academic role by exact Discord name and academic color."""
        role = discord.utils.get(self.guild.roles, name=name)
        if role is None:
            raise ValueError(f"Academic role '{name}' not found")
        if role.color.value != self.ACADEMIC_ROLE_COLOR:
            raise ValueError(
                f"Academic role '{name}' has color {role.color.value:#x}, expected {self.ACADEMIC_ROLE_COLOR:#x}"
            )
        return role

    def get_channel(self, name: str) -> discord.TextChannel | discord.Thread:
        """Get channel or thread by config name."""
        channel_id = self.CHANNELS.get(name)
        if channel_id is None:
            raise ValueError(f"Channel '{name}' not found")
        channel = self.guild.get_channel_or_thread(channel_id)
        if isinstance(channel, discord.TextChannel | discord.Thread):
            return channel
        raise ValueError(f"Channel with ID {channel_id} not found")

    # Convenience methods for common roles

    @property
    def admin_role(self) -> discord.Role:
        """Get admin role."""
        return self.get_role("ADMIN")

    @property
    def mod_role(self) -> discord.Role:
        """Get moderator role."""
        return self.get_role("MOD")

    @property
    def junior_mod_role(self) -> discord.Role:
        """Get junior moderator role."""
        return self.get_role("JUNIOR_MOD")

    @property
    def bot_dev_role(self) -> discord.Role:
        """Get bot developer role."""
        return self.get_role("BOT_DEV")

    @property
    def linked_role(self) -> discord.Role:
        """Get linked role."""
        return self.get_role("LINKED")

    @property
    def just_joined_role(self) -> discord.Role:
        """Get just joined role."""
        return self.get_role("JUST_JOINED")

    @property
    def muted_role(self) -> discord.Role:
        """Get muted role."""
        return self.get_role("MUTED")

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
    def lobby_channel(self) -> discord.TextChannel:
        """Get lobby channel."""
        channel = self.get_channel("LOBBY")
        if not isinstance(channel, discord.TextChannel):
            raise ValueError("LOBBY must be a text channel")
        return channel

    @property
    def verification_logs_channel(self) -> discord.TextChannel | discord.Thread:
        """Get verification logs thread/channel."""
        return self.get_channel("VERIFICATION_LOGS")

    @property
    def error_logs_channel(self) -> discord.TextChannel | discord.Thread:
        """Get error logs thread/channel."""
        return self.get_channel("ERROR_LOGS")

    @property
    def honeypot_channel(self) -> discord.TextChannel | discord.Thread:
        """Get honeypot channel."""
        return self.get_channel("HONEYPOT")
