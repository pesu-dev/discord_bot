from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Self

from src.data.mongo._base import TypedCollection, omit_none, parse_object_id

if TYPE_CHECKING:
    from collections.abc import AsyncIterator
    from datetime import datetime

    from bson import ObjectId


@dataclass
class AnonBan:
    """Document in the `anonban` collection."""

    user_id: str
    reason: str
    banned_at: datetime
    active: bool
    expires_at: datetime | None = None
    id: ObjectId | None = None

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> Self:
        return cls(
            id=parse_object_id(doc),
            user_id=doc["userId"],
            reason=doc["reason"],
            banned_at=doc["bannedAt"],
            active=doc["active"],
            expires_at=doc.get("expiresAt"),
        )

    def to_document(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "userId": self.user_id,
            "reason": self.reason,
            "bannedAt": self.banned_at,
            "expiresAt": self.expires_at,
            "active": self.active,
        }
        if self.id is not None:
            doc["_id"] = self.id
        return omit_none(doc)


class AnonBanStore(TypedCollection[AnonBan]):
    """Store for the `anonban` collection."""

    model = AnonBan
    field_map: ClassVar[dict[str, str]] = {
        "id": "_id",
        "user_id": "userId",
        "reason": "reason",
        "banned_at": "bannedAt",
        "expires_at": "expiresAt",
        "active": "active",
    }

    async def find_expired(self, now: datetime) -> AsyncIterator[AnonBan]:
        """Active bans whose expires_at is set and in the past."""
        query = {"expiresAt": {"$ne": None, "$lt": now}, "active": True}
        async for doc in self._collection.find(query):
            yield AnonBan.from_document(doc)

    async def deactivate(self, user_id: str) -> AnonBan | None:
        """Deactivate the active ban for a user, returning the pre-update document."""
        return await self.find_one_and_update(
            user_id=user_id,
            active=True,
            set_fields={"active": False},
        )
