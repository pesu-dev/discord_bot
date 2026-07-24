from __future__ import annotations

from typing import TYPE_CHECKING

from src.data.mongo.anonban import AnonBanStore
from src.data.mongo.link import LinkStore
from src.data.mongo.mute import MuteStore
from src.data.mongo.student import StudentStore

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase


class Stores:
    """Typed collection stores for the bot's MongoDB database."""

    def __init__(self, db: AsyncDatabase) -> None:
        self.links = LinkStore(db["link"])
        self.students = StudentStore(db["student"])
        self.anonbans = AnonBanStore(db["anonban"])
        self.mutes = MuteStore(db["mute"])
