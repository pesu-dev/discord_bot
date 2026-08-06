from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from src.data.mongo._base import TypedCollection
from src.data.mongo.collections.anon_bans import AnonBanStore
from src.data.mongo.collections.anon_mutes import AnonMuteStore
from src.data.mongo.collections.links import LinkStore
from src.data.mongo.collections.mutes import MuteStore
from src.data.mongo.collections.students import StudentStore

if TYPE_CHECKING:
    from pymongo.asynchronous.database import AsyncDatabase

StoreT = TypeVar("StoreT", bound=TypedCollection)


class Stores:
    """Typed collection stores for the bot's MongoDB database."""

    links: LinkStore
    students: StudentStore
    mutes: MuteStore
    anon_mutes: AnonMuteStore
    anon_bans: AnonBanStore
    _stores: list[TypedCollection]

    def __init__(self, db: AsyncDatabase) -> None:
        self._stores = []
        self.links = self._bind(db, "links", LinkStore)
        self.students = self._bind(db, "students", StudentStore)
        self.mutes = self._bind(db, "mutes", MuteStore)
        self.anon_mutes = self._bind(db, "anon_mutes", AnonMuteStore)
        self.anon_bans = self._bind(db, "anon_bans", AnonBanStore)

    def _bind(self, db: AsyncDatabase, name: str, store_cls: type[StoreT]) -> StoreT:
        """Open ``name``; if the store sets ``has_archive``, also open its archive twin."""
        hot = store_cls(db[name])
        self._stores.append(hot)
        if store_cls.has_archive:
            archived = store_cls(db[f"archive.{name}"])
            # Twin is the same store class, but it is not itself archived further.
            archived.has_archive = False
            hot.archive = archived
            self._stores.append(archived)
        return hot

    async def sync_archives(self) -> dict[str, int]:
        """Upsert all hot docs into their archive twins by ``_id``."""
        counts: dict[str, int] = {}
        for store in self._stores:
            if not store.has_archive:
                continue
            counts[store.archive.name] = await store.replace_upsert_into(store.archive)
        return counts

    @classmethod
    async def create(cls, db: AsyncDatabase) -> Stores:
        """Build stores and create all declared indexes (idempotent)."""
        stores = cls(db)
        for store in stores._stores:
            await store.ensure_indexes()
        return stores
