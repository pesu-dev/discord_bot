from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Self

from src.data.mongo._base import TypedCollection, omit_none, parse_object_id

if TYPE_CHECKING:
    from datetime import datetime

    from bson import ObjectId


@dataclass
class Link:
    """Document in the `link` collection."""

    user_id: str
    prn: str
    linked_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: ObjectId | None = None

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> Self:
        return cls(
            id=parse_object_id(doc),
            user_id=doc["userId"],
            prn=doc["prn"],
            linked_at=doc.get("linkedAt"),
            created_at=doc.get("createdAt"),
            updated_at=doc.get("updatedAt"),
        )

    def to_document(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "userId": self.user_id,
            "prn": self.prn,
            "linkedAt": self.linked_at,
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
        if self.id is not None:
            doc["_id"] = self.id
        return omit_none(doc)


class LinkStore(TypedCollection[Link]):
    """Store for the `link` collection."""

    model = Link
    field_map: ClassVar[dict[str, str]] = {
        "id": "_id",
        "user_id": "userId",
        "prn": "prn",
        "linked_at": "linkedAt",
        "created_at": "createdAt",
        "updated_at": "updatedAt",
    }
