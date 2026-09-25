from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Self

from src.data.mongo._base import IndexSpec, TypedCollection, omit_none, parse_object_id
from src.utils import general as ug

if TYPE_CHECKING:
    from datetime import datetime

    from bson import ObjectId
    from pymongo.results import DeleteResult


@dataclass
class ServerBan:
    """Document in the `server_bans` collection.

    Identity-level server ban keyed by verified PESU PRN, so a banned user
    cannot evade via a new Discord account. The Discord user ID is kept for
    audit history only; enforcement always matches on ``prn``.
    """

    prn: str
    discord_user_id: str
    reason: str
    banned_at: datetime
    id: ObjectId | None = None

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> Self:
        return cls(
            id=parse_object_id(doc),
            prn=doc["prn"],
            discord_user_id=str(doc["discord_user_id"]),
            reason=doc["reason"],
            banned_at=doc["banned_at"],
        )

    def to_document(self) -> dict[str, Any]:
        canonical_prn = ug.validate_prn(self.prn)
        if canonical_prn is None:
            msg = "ServerBan.prn must be a valid canonical PESU PRN"
            raise ValueError(msg)
        doc: dict[str, Any] = {
            "prn": canonical_prn,
            "discord_user_id": self.discord_user_id,
            "reason": self.reason,
            "banned_at": self.banned_at,
        }
        if self.id is not None:
            doc["_id"] = self.id
        return omit_none(doc)


class ServerBanStore(TypedCollection[ServerBan]):
    """Store for the `server_bans` collection."""

    model = ServerBan
    has_archive = False
    field_map: ClassVar[dict[str, str]] = {
        "id": "_id",
        "prn": "prn",
        "discord_user_id": "discord_user_id",
        "reason": "reason",
        "banned_at": "banned_at",
    }
    indexes: ClassVar[list[IndexSpec]] = [
        ([("prn", 1)], {"unique": True, "name": "server_bans_prn_key"}),
        ([("discord_user_id", 1)], {"name": "server_bans_discord_user_id_idx"}),
    ]

    async def has_active(self, prn: object) -> bool:
        """Return whether the canonical PRN has an active server ban identity."""
        canonical = ug.validate_prn(prn)
        if canonical is None:
            return False
        return await self.exists(prn=canonical)

    async def remove_ban(self, prn: object) -> bool:
        """Remove the identity ban for a canonical PRN. Idempotent: False when absent/invalid."""
        canonical = ug.validate_prn(prn)
        if canonical is None:
            return False
        result: DeleteResult = await self.delete_one(prn=canonical)
        return result.deleted_count > 0

    async def remove_ban_for_user(self, prn: object, discord_user_id: str) -> bool:
        """Remove a ban only when both its canonical PRN and Discord ID match.

        The extra predicate prevents an unban from deleting a different account's
        identity record if legacy data has been corrupted or changed concurrently.
        """
        canonical = ug.validate_prn(prn)
        if canonical is None:
            return False
        result: DeleteResult = await self.delete_one(prn=canonical, discord_user_id=discord_user_id)
        return result.deleted_count > 0
