from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any, ClassVar, Self

from src.data.mongo._base import IndexSpec, TypedCollection, omit_none, parse_object_id

if TYPE_CHECKING:
    from datetime import datetime

    from bson import ObjectId
    from pymongo.results import DeleteResult, UpdateResult


@dataclass
class AnonMute:
    """Document in the `anon_mutes` collection."""

    discord_user_id: str
    moderator_discord_user_id: str
    muted_at: datetime
    original_unmute_time: datetime
    reason: str
    unmuted_at: datetime | None = None
    id: ObjectId | None = None

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> Self:
        return cls(
            id=parse_object_id(doc),
            discord_user_id=str(doc["discord_user_id"]),
            moderator_discord_user_id=str(doc["moderator_discord_user_id"]),
            muted_at=doc["muted_at"],
            original_unmute_time=doc["original_unmute_time"],
            reason=doc["reason"],
            unmuted_at=doc.get("unmuted_at"),
        )

    def to_document(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "discord_user_id": self.discord_user_id,
            "moderator_discord_user_id": self.moderator_discord_user_id,
            "muted_at": self.muted_at,
            "original_unmute_time": self.original_unmute_time,
            "reason": self.reason,
            "unmuted_at": self.unmuted_at,
        }
        if self.id is not None:
            doc["_id"] = self.id
        return omit_none(doc)


class AnonMuteStore(TypedCollection[AnonMute]):
    """Store for the `anon_mutes` collection."""

    model = AnonMute
    has_archive = True
    field_map: ClassVar[dict[str, str]] = {
        "id": "_id",
        "discord_user_id": "discord_user_id",
        "moderator_discord_user_id": "moderator_discord_user_id",
        "muted_at": "muted_at",
        "original_unmute_time": "original_unmute_time",
        "reason": "reason",
        "unmuted_at": "unmuted_at",
    }
    indexes: ClassVar[list[IndexSpec]] = [
        (
            [("unmuted_at", 1), ("original_unmute_time", 1)],
            {"name": "anon_mutes_unmuted_at_original_unmute_time_idx"},
        ),
        (
            [("discord_user_id", 1), ("unmuted_at", 1)],
            {"name": "anon_mutes_discord_user_id_unmuted_at_idx"},
        ),
        ([("unmuted_at", 1)], {"name": "anon_mutes_unmuted_at_idx"}),
    ]

    async def has_active(self, discord_user_id: str) -> bool:
        """Return whether the user has an active anon mute."""
        return await self.exists(discord_user_id=discord_user_id, unmuted_at=None)

    async def find_active(self, discord_user_id: str) -> AnonMute | None:
        """Return the active anon mute for a user, if any."""
        return await self.find_one(discord_user_id=discord_user_id, unmuted_at=None)

    async def find_expired(self, now: datetime, *, limit: int = 100) -> list[AnonMute]:
        """Active anon mutes whose original_unmute_time is at or before now."""
        cursor = self._collection.find(
            {"unmuted_at": None, "original_unmute_time": {"$lte": now}},
        )
        docs = await cursor.to_list(length=limit)
        return [AnonMute.from_document(doc) for doc in docs]

    async def mark_unmuted(self, mute_id: ObjectId, *, unmuted_at: datetime) -> UpdateResult:
        """Mark a single anon mute as lifted."""
        return await self.update_one(id=mute_id, set_fields={"unmuted_at": unmuted_at})

    async def unmute_user(self, discord_user_id: str, *, unmuted_at: datetime) -> UpdateResult:
        """Mark all active anon mutes for a user as lifted."""
        return await self.update_many(
            discord_user_id=discord_user_id,
            unmuted_at=None,
            set_fields={"unmuted_at": unmuted_at},
        )

    async def delete_stale(self, now: datetime, *, retention: timedelta = timedelta(days=1)) -> DeleteResult:
        """Delete anon mutes unmuted at least `retention` ago."""
        return await self._collection.delete_many({"unmuted_at": {"$lte": now - retention}})
