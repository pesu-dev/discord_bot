from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any, ClassVar, Self
from uuid import uuid4

from src.data.mongo._base import IndexSpec, TypedCollection, omit_none, parse_object_id
from src.utils import general as ug

logger = logging.getLogger(__name__)

if TYPE_CHECKING:
    from bson import ObjectId


@dataclass
class PendingServerBan:
    """Document in the `pending_server_bans` collection.

    Durable retry record for a PRN identity operation that survived a partial
    failure (e.g. Discord ban applied but the identity write failed). A background
    loop reconciles these until the identity store converges, then deletes them.
    ``op`` records the moderator action that encountered the partial failure.
    Reconciliation does not replay it: Discord's current ban state is the
    authority. ``operation_id`` makes completion/retry updates conditional so an
    older worker cannot delete or overwrite a newer desired state.
    """

    op: str
    prn: str
    discord_user_id: str
    reason: str
    failed_at: datetime
    operation_id: str = field(default_factory=lambda: uuid4().hex)
    attempt_count: int = 0
    last_attempt_at: datetime | None = None
    next_retry_at: datetime | None = None
    last_error: str | None = None
    id: ObjectId | None = None

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> Self:
        return cls(
            id=parse_object_id(doc),
            op=doc["op"],
            prn=doc["prn"],
            discord_user_id=str(doc["discord_user_id"]),
            reason=doc["reason"],
            failed_at=doc["failed_at"],
            operation_id=doc.get("operation_id", str(doc.get("_id", "legacy"))),
            attempt_count=int(doc.get("attempt_count", 0)),
            last_attempt_at=doc.get("last_attempt_at"),
            next_retry_at=doc.get("next_retry_at"),
            last_error=doc.get("last_error"),
        )

    def to_document(self) -> dict[str, Any]:
        canonical_prn = ug.validate_prn(self.prn)
        if canonical_prn is None:
            msg = "PendingServerBan.prn must be a valid canonical PESU PRN"
            raise ValueError(msg)
        doc: dict[str, Any] = {
            "op": self.op,
            "prn": canonical_prn,
            "discord_user_id": self.discord_user_id,
            "reason": self.reason,
            "failed_at": self.failed_at,
            "operation_id": self.operation_id,
            "attempt_count": self.attempt_count,
            "last_attempt_at": self.last_attempt_at,
            "next_retry_at": self.next_retry_at,
            "last_error": self.last_error,
        }
        if self.id is not None:
            doc["_id"] = self.id
        return omit_none(doc)


class PendingServerBanStore(TypedCollection[PendingServerBan]):
    """Store for the `pending_server_bans` collection."""

    model = PendingServerBan
    has_archive = False
    field_map: ClassVar[dict[str, str]] = {
        "id": "_id",
        "op": "op",
        "prn": "prn",
        "discord_user_id": "discord_user_id",
        "reason": "reason",
        "failed_at": "failed_at",
        "operation_id": "operation_id",
        "attempt_count": "attempt_count",
        "last_attempt_at": "last_attempt_at",
        "next_retry_at": "next_retry_at",
        "last_error": "last_error",
    }
    indexes: ClassVar[list[IndexSpec]] = [
        (
            [("discord_user_id", 1)],
            {
                "unique": True,
                "name": "pending_server_bans_discord_user_id_key",
                "partialFilterExpression": {"discord_user_id": {"$type": "string"}},
            },
        ),
        ([("failed_at", 1)], {"name": "pending_server_bans_failed_at_idx"}),
        ([("next_retry_at", 1)], {"name": "pending_server_bans_next_retry_at_idx"}),
    ]

    async def list_pending(self, *, limit: int = 100, now: datetime | None = None) -> list[PendingServerBan]:
        """Return retryable pending operations, oldest first."""
        now = now or datetime.now(UTC)
        pending = await self.find_many()
        eligible = [record for record in pending if record.next_retry_at is None or record.next_retry_at <= now]
        return sorted(eligible, key=lambda record: record.failed_at)[:limit]

    async def ensure_indexes(self) -> None:
        """Keep only the newest legacy record per account before adding uniqueness.

        Earlier records are historical retry instructions. Retaining the most
        recent desired state is both deterministic and prevents an upgrade from
        leaving stale operations capable of being processed.
        """
        seen: set[str] = set()
        cursor = self._collection.find({"discord_user_id": {"$type": "string"}}).sort([("failed_at", -1), ("_id", -1)])
        async for doc in cursor:
            discord_user_id = doc["discord_user_id"]
            if discord_user_id in seen:
                await self._collection.delete_one({"_id": doc["_id"]})
                logger.warning("Discarded stale duplicate pending identity operation for user %s", discord_user_id)
            else:
                seen.add(discord_user_id)
        await super().ensure_indexes()

    async def replace_current(self, record: PendingServerBan) -> None:
        """Atomically replace the latest desired state for one Discord account."""
        document = record.to_document()
        document.pop("_id", None)
        await self._collection.update_one(
            {"discord_user_id": record.discord_user_id},
            {"$set": document},
            upsert=True,
        )

    async def delete_if_current(self, record: PendingServerBan) -> bool:
        """Delete only the operation that was reconciled, not a newer replacement."""
        if record.id is None:
            return False
        result = await self._collection.delete_one({"_id": record.id, "operation_id": record.operation_id})
        return result.deleted_count > 0

    async def mark_retry_failure(self, record: PendingServerBan, error: str) -> None:
        """Record a bounded exponential backoff without overwriting newer intent."""
        if record.id is None:
            return
        now = datetime.now(UTC)
        attempts = record.attempt_count + 1
        delay = min(300 * (2 ** min(attempts - 1, 4)), 3600)
        await self._collection.update_one(
            {"_id": record.id, "operation_id": record.operation_id},
            {
                "$set": {
                    "attempt_count": attempts,
                    "last_attempt_at": now,
                    "next_retry_at": now + timedelta(seconds=delay),
                    "last_error": error[:1000],
                }
            },
        )
