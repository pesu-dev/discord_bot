import os
import time
from pathlib import Path

import discord
from discord import Intents
from discord.app_commands import CommandTree
from dotenv import load_dotenv
from pymongo import AsyncMongoClient

from bot import DiscordBot
from utils.config import Config

load_dotenv()


bot_prefix = os.getenv("BOT_PREFIX")

client = DiscordBot(
    command_prefix=bot_prefix,
    help_command=None,
    intents=Intents().all(),
    tree_cls=CommandTree,
)

connection = ""

try:
    client.mongo_client = AsyncMongoClient(os.environ["MONGO_URI"], tz_aware=True)
    db_name = os.environ["DB_NAME"]
    client.db = client.mongo_client[db_name]
    client.link_collection = client.db["link"]
    client.student_collection = client.db["student"]
    client.anonban_collection = client.db["anonban"]
    client.mute_collection = client.db["mute"]

    connection = "Connected to MongoDB"
except Exception as e:
    connection = f"Failed to connect to MongoDB: {e}"


@client.event
async def on_ready() -> None:
    client.startTime = time.time()
    if client.user:
        client.logger.info(f"Logged in as {client.user.name} ({client.user.id})")
    client.logger.info(connection)

    # Initialize the config instance after bot is ready
    client.config = Config(client)
    client.logger.info("Config initialized")

    # Clear all commands
    # await clear_all_commands(client=client)

    # Load cogs
    for path in Path("cogs").rglob("*.py"):
        if path.name.startswith("__"):
            continue

        cog = ".".join(path.with_suffix("").parts)
        try:
            await client.load_extension(cog)
            client.logger.info(f"Loaded {cog}")
        except Exception as e:
            client.logger.error(f"Failed to load {cog}: {e}")

    # Sync commands
    # await sync_all_commands(client=client)

    # Set status
    await client.change_presence(
        activity=discord.Activity(
            type=discord.ActivityType.watching,
            name="students suffer",
        )
    )
    client.logger.info("Set status")
    client.logger.info("Bot is ready")

    await client.config.bot_logs_channel.send("Bot is online")


async def clear_all_commands(client: DiscordBot) -> None:
    """Clear all guild commands"""
    guild = client.config.guild
    try:
        # Clear all guild commands
        client.tree.clear_commands(guild=guild)
        await client.tree.sync(guild=guild)
        client.logger.info("Cleared all guild commands")
    except Exception as e:
        client.logger.error(f"Failed to clear guild commands: {e}")


async def sync_all_commands(client: DiscordBot) -> None:
    """Sync all commands to the guild"""
    guild = client.config.guild
    try:
        await client.tree.sync(guild=guild)
        client.logger.info("Synced all commands to the guild")
    except Exception as e:
        client.logger.error(f"Failed to sync commands: {e}")


bot_token = os.getenv("BOT_TOKEN")
if bot_token:
    client.run(bot_token)
else:
    client.logger.error("BOT_TOKEN environment variable not set")
