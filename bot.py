import logging
from typing import TYPE_CHECKING

from discord.ext import commands

if TYPE_CHECKING:
    from pymongo import AsyncMongoClient
    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.asynchronous.database import AsyncDatabase

    from utils.config import Config


class DiscordBot(commands.Bot):
    def __init__(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        super().__init__(*args, **kwargs)
        self.mongo_client: AsyncMongoClient
        self.db: AsyncDatabase
        self.link_collection: AsyncCollection
        self.student_collection: AsyncCollection
        self.anonban_collection: AsyncCollection
        self.mute_collection: AsyncCollection
        self.startTime: float
        self.logger = logging.getLogger("discord.app")
        self.config: Config
