from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Self

from src.data.mongo._base import TypedCollection, omit_none, parse_object_id

if TYPE_CHECKING:
    from datetime import datetime

    from bson import ObjectId


@dataclass
class Branch:
    """Nested branch on a student document."""

    full: str
    short: str

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> Self:
        return cls(full=doc["full"], short=doc["short"])

    def to_document(self) -> dict[str, Any]:
        return {"full": self.full, "short": self.short}


@dataclass
class Campus:
    """Nested campus on a student document."""

    code: int
    short: str

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> Self:
        return cls(code=int(doc["code"]), short=doc["short"])

    def to_document(self) -> dict[str, Any]:
        return {"code": self.code, "short": self.short}


@dataclass
class Student:
    """Document in the `student` collection."""

    prn: str
    branch: Branch
    year: str
    campus: Campus
    created_at: datetime | None = None
    updated_at: datetime | None = None
    id: ObjectId | None = None

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> Self:
        return cls(
            id=parse_object_id(doc),
            prn=doc["prn"],
            branch=Branch.from_document(doc["branch"]),
            year=doc["year"],
            campus=Campus.from_document(doc["campus"]),
            created_at=doc.get("createdAt"),
            updated_at=doc.get("updatedAt"),
        )

    def to_document(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "prn": self.prn,
            "branch": self.branch.to_document(),
            "year": self.year,
            "campus": self.campus.to_document(),
            "createdAt": self.created_at,
            "updatedAt": self.updated_at,
        }
        if self.id is not None:
            doc["_id"] = self.id
        return omit_none(doc)


class StudentStore(TypedCollection[Student]):
    """Store for the `student` collection."""

    model = Student
    field_map: ClassVar[dict[str, str]] = {
        "id": "_id",
        "prn": "prn",
        "branch": "branch",
        "year": "year",
        "campus": "campus",
        "created_at": "createdAt",
        "updated_at": "updatedAt",
    }
