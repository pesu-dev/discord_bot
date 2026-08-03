from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Self

from src.data.mongo._base import TypedCollection, omit_none, parse_object_id

if TYPE_CHECKING:
    from datetime import datetime

    from bson import ObjectId
    from pymongo.results import UpdateResult


@dataclass
class Mute:
    """Document in the `mute` collection."""

    user_id: int
    channel_id: int
    moderator_id: int
    mute_time: datetime
    unmute_time: datetime
    reason: str
    active: bool
    is_self_mute: bool
    duration_seconds: int | None = None
    unmute_type: str | None = None
    unmuted_by: int | None = None
    id: ObjectId | None = None

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> Self:
        return cls(
            id=parse_object_id(doc),
            user_id=int(doc["user_id"]),
            channel_id=int(doc["channel_id"]),
            moderator_id=int(doc["moderator_id"]),
            mute_time=doc["mute_time"],
            unmute_time=doc["unmute_time"],
            reason=doc["reason"],
            active=doc["active"],
            is_self_mute=doc["is_self_mute"],
            duration_seconds=doc.get("duration_seconds"),
            unmute_type=doc.get("unmute_type"),
            unmuted_by=int(doc["unmuted_by"]) if doc.get("unmuted_by") is not None else None,
        )

    def to_document(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "user_id": self.user_id,
            "channel_id": self.channel_id,
            "moderator_id": self.moderator_id,
            "mute_time": self.mute_time,
            "unmute_time": self.unmute_time,
            "duration_seconds": self.duration_seconds,
            "reason": self.reason,
            "active": self.active,
            "is_self_mute": self.is_self_mute,
            "unmute_type": self.unmute_type,
            "unmuted_by": self.unmuted_by,
        }
        if self.id is not None:
            doc["_id"] = self.id
        return omit_none(doc)


class MuteStore(TypedCollection[Mute]):
    """Store for the `mute` collection."""

    model = Mute
    field_map: ClassVar[dict[str, str]] = {
        "id": "_id",
        "user_id": "user_id",
        "channel_id": "channel_id",
        "moderator_id": "moderator_id",
        "mute_time": "mute_time",
        "unmute_time": "unmute_time",
        "duration_seconds": "duration_seconds",
        "reason": "reason",
        "active": "active",
        "is_self_mute": "is_self_mute",
        "unmute_type": "unmute_type",
        "unmuted_by": "unmuted_by",
    }

    async def find_expired(self, now: datetime, *, limit: int = 100) -> list[Mute]:
        """Active mutes whose unmute_time is at or before now."""
        cursor = self._collection.find({"unmute_time": {"$lte": now}, "active": True})
        docs = await cursor.to_list(length=limit)
        return [Mute.from_document(doc) for doc in docs]

    async def mark_unmuted(
        self,
        mute_id: ObjectId,
        *,
        unmute_time: datetime,
        unmute_type: str,
        unmuted_by: int | None = None,
    ) -> UpdateResult:
        """Mark a single mute inactive with unmute metadata."""
        set_fields: dict[str, object] = {
            "active": False,
            "unmute_time": unmute_time,
            "unmute_type": unmute_type,
        }
        if unmuted_by is not None:
            set_fields["unmuted_by"] = unmuted_by
        return await self.update_one(id=mute_id, set_fields=set_fields)

    async def deactivate_active(
        self,
        user_id: int,
        *,
        unmute_time: datetime,
        unmute_type: str,
        unmuted_by: int,
    ) -> UpdateResult:
        """Deactivate all active mutes for a user (manual unmute)."""
        return await self.update_many(
            user_id=user_id,
            active=True,
            set_fields={
                "active": False,
                "unmute_time": unmute_time,
                "unmute_type": unmute_type,
                "unmuted_by": unmuted_by,
            },
        )
