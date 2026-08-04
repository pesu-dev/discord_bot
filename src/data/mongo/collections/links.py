from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Self

from src.data.mongo._base import IndexSpec, TypedCollection, omit_none, parse_object_id

if TYPE_CHECKING:
    from datetime import datetime

    from bson import ObjectId


@dataclass
class Link:
    """Document in the `links` collection."""

    discord_user_id: str
    prn: str
    linked_at: datetime | None = None
    id: ObjectId | None = None

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> Self:
        return cls(
            id=parse_object_id(doc),
            discord_user_id=str(doc["discord_user_id"]),
            prn=doc["prn"],
            linked_at=doc.get("linked_at"),
        )

    def to_document(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "discord_user_id": self.discord_user_id,
            "prn": self.prn,
            "linked_at": self.linked_at,
        }
        if self.id is not None:
            doc["_id"] = self.id
        return omit_none(doc)


class LinkStore(TypedCollection[Link]):
    """Store for the `links` collection."""

    model = Link
    field_map: ClassVar[dict[str, str]] = {
        "id": "_id",
        "discord_user_id": "discord_user_id",
        "prn": "prn",
        "linked_at": "linked_at",
    }
    indexes: ClassVar[list[IndexSpec]] = [
        ([("discord_user_id", 1)], {"unique": True, "name": "links_discord_user_id_key"}),
        ([("prn", 1)], {"unique": True, "name": "links_prn_key"}),
    ]
