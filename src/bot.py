import logging
import os
import platform
import random
import time
from pathlib import Path
from typing import TYPE_CHECKING

import discord
from discord import Intents
from discord.app_commands import CommandTree
from discord.ext import commands, tasks
from discord.ext.commands import Context
from pymongo import AsyncMongoClient

from src.utils.config import Config

if TYPE_CHECKING:
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase


class DiscordBot(commands.Bot):
    # Rotating presence shown by the status task.
    STATUSES = (
        discord.Activity(type=discord.ActivityType.watching, name="students suffer"),
        discord.Activity(type=discord.ActivityType.watching, name="terrible vibe-coders struggling"),
        discord.Activity(type=discord.ActivityType.listening, name="/help"),
    )

    def __init__(self) -> None:
        _, prefix, _ = Config.resolve_env()
        super().__init__(
            command_prefix=prefix,
            help_command=None,
            intents=Intents.all(),
            tree_cls=CommandTree,
        )
        self.logger = logging.getLogger("discord.app")
        self.config = Config(self)

        self.mongo_client: AsyncMongoClient
        self.db: AsyncDatabase
        self.link_collection: AsyncCollection
        self.student_collection: AsyncCollection
        self.anonban_collection: AsyncCollection
        self.mute_collection: AsyncCollection
        self.startTime: float = time.time()
        self.db_status: str = ""

    async def init_db(self) -> None:
        """Connect to MongoDB and wire up collections."""
        try:
            self.mongo_client = AsyncMongoClient(os.environ["MONGO_URI"], tz_aware=True)
            self.db = self.mongo_client[self.config.db_name]
            self.link_collection = self.db["link"]
            self.student_collection = self.db["student"]
            self.anonban_collection = self.db["anonban"]
            self.mute_collection = self.db["mute"]
            self.db_status = f"Connected to MongoDB ({self.config.db_name})"
        except Exception as e:
            self.db_status = f"Failed to connect to MongoDB: {e}"
        self.logger.info(self.db_status)

    async def load_cogs(self) -> None:
        """Load every cog in the flat cogs/ directory."""
        cogs_dir = Path(__file__).resolve().parent / "cogs"
        for file in sorted(os.listdir(cogs_dir)):
            if not file.endswith(".py") or file.startswith("__"):
                continue
            extension = file[:-3]
            try:
                await self.load_extension(f"{__package__}.cogs.{extension}")
                self.logger.info(f"Loaded extension '{extension}'")
            except Exception as e:
                self.logger.error(f"Failed to load extension '{extension}': {type(e).__name__}: {e}")

    @tasks.loop(minutes=5.0)
    async def status_task(self) -> None:
        await self.change_presence(activity=random.choice(self.STATUSES))

    @status_task.before_loop
    async def before_status_task(self) -> None:
        await self.wait_until_ready()

    async def setup_hook(self) -> None:
        """Runs once at startup, before the bot is ready."""
        self.logger.info(f"Running in '{self.config.env}' environment")
        self.logger.info(f"discord.py API version: {discord.__version__}")
        self.logger.info(f"Python version: {platform.python_version()}")
        self.logger.info(f"Running on: {platform.system()} {platform.release()} ({os.name})")
        self.logger.info("-------------------")
        await self.init_db()
        await self.load_cogs()
        self.status_task.start()

    async def on_ready(self) -> None:
        self.startTime = time.time()
        if self.user:
            self.logger.info(f"Logged in as {self.user.name} ({self.user.id})")
        self.logger.info("Bot is ready")
        try:
            await self.config.bot_logs_channel.send("Bot is online")
        except Exception as e:
            self.logger.error(f"Failed to send online message: {e}")

    async def on_command_completion(self, context: Context) -> None:
        if context.command is None:
            return
        executed = context.command.qualified_name
        if context.guild is not None:
            self.logger.info(
                f"Executed '{executed}' by {context.author} (ID: {context.author.id}) "
                f"in {context.guild.name} (ID: {context.guild.id})"
            )
        else:
            self.logger.info(f"Executed '{executed}' by {context.author} (ID: {context.author.id}) in DMs")

    async def on_command_error(self, context: Context, error: commands.CommandError) -> None:
        # Defer to a command/cog-specific handler if one exists.
        if context.command and context.command.has_error_handler():
            return
        if context.cog and context.cog.has_error_handler():
            return

        if isinstance(error, commands.CommandNotFound):
            return
        if isinstance(error, commands.MissingRequiredArgument):
            await context.send(f"Missing required argument: `{error.param.name}`")
        elif isinstance(error, commands.MissingPermissions):
            await context.send(
                "You are missing the permission(s) `" + ", ".join(error.missing_permissions) + "` to run this command."
            )
        elif isinstance(error, commands.BotMissingPermissions):
            await context.send(
                "I am missing the permission(s) `" + ", ".join(error.missing_permissions) + "` to run this command."
            )
        else:
            self.logger.error(f"Unhandled command error in '{context.command}': {type(error).__name__}: {error}")
