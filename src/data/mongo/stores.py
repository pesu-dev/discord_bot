from __future__ import annotations

from typing import TYPE_CHECKING

from src.data.mongo.collections.anon_bans import AnonBanStore
from src.data.mongo.collections.anon_mutes import AnonMuteStore
from src.data.mongo.collections.links import LinkStore
from src.data.mongo.collections.mutes import MuteStore
from src.data.mongo.collections.students import StudentStore

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase


class Stores:
    """Typed collection stores for the bot's MongoDB database."""

    def __init__(self, db: AsyncDatabase) -> None:
        self.links = LinkStore(db["links"])
        self.students = StudentStore(db["students"])
        self.anon_bans = AnonBanStore(db["anon_bans"])
        self.anon_mutes = AnonMuteStore(db["anon_mutes"])
        self.mutes = MuteStore(db["mutes"])

    @classmethod
    async def create(cls, db: AsyncDatabase) -> Stores:
        """Build stores and create all declared indexes (idempotent)."""
        stores = cls(db)
        await stores.links.ensure_indexes()
        await stores.students.ensure_indexes()
        await stores.anon_bans.ensure_indexes()
        await stores.anon_mutes.ensure_indexes()
        await stores.mutes.ensure_indexes()
        return stores
