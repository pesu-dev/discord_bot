from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import TYPE_CHECKING, Any, ClassVar, Self

from src.data.mongo._base import IndexSpec, TypedCollection, omit_none, parse_object_id

if TYPE_CHECKING:
    from datetime import datetime

    from bson import ObjectId
    from pymongo.results import DeleteResult


@dataclass
class AnonBan:
    """Document in the `anon_bans` collection."""

    discord_user_id: str
    reason: str
    banned_at: datetime
    unbanned_at: datetime | None = None
    id: ObjectId | None = None

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> Self:
        return cls(
            id=parse_object_id(doc),
            discord_user_id=str(doc["discord_user_id"]),
            reason=doc["reason"],
            banned_at=doc["banned_at"],
            unbanned_at=doc.get("unbanned_at"),
        )

    def to_document(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "discord_user_id": self.discord_user_id,
            "reason": self.reason,
            "banned_at": self.banned_at,
            "unbanned_at": self.unbanned_at,
        }
        if self.id is not None:
            doc["_id"] = self.id
        return omit_none(doc)


class AnonBanStore(TypedCollection[AnonBan]):
    """Store for the `anon_bans` collection."""

    model = AnonBan
    has_archive = True
    field_map: ClassVar[dict[str, str]] = {
        "id": "_id",
        "discord_user_id": "discord_user_id",
        "reason": "reason",
        "banned_at": "banned_at",
        "unbanned_at": "unbanned_at",
    }
    indexes: ClassVar[list[IndexSpec]] = [
        (
            [("discord_user_id", 1), ("unbanned_at", 1)],
            {"name": "anon_bans_discord_user_id_unbanned_at_idx"},
        ),
        ([("unbanned_at", 1)], {"name": "anon_bans_unbanned_at_idx"}),
    ]

    async def has_active(self, discord_user_id: str) -> bool:
        """Return whether the user has an active anon ban."""
        return await self.exists(discord_user_id=discord_user_id, unbanned_at=None)

    async def find_active(self, discord_user_id: str) -> AnonBan | None:
        """Return the active anon ban for a user, if any."""
        return await self.find_one(discord_user_id=discord_user_id, unbanned_at=None)

    async def unban(self, discord_user_id: str, *, unbanned_at: datetime) -> AnonBan | None:
        """Mark the active ban as lifted, returning the pre-update document."""
        return await self.find_one_and_update(
            discord_user_id=discord_user_id,
            unbanned_at=None,
            set_fields={"unbanned_at": unbanned_at},
        )

    async def delete_stale(self, now: datetime, *, retention: timedelta = timedelta(days=1)) -> DeleteResult:
        """Delete bans unbanned at least `retention` ago."""
        return await self._collection.delete_many({"unbanned_at": {"$lte": now - retention}})
