from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Self

from src.data.mongo._base import IndexSpec, TypedCollection, omit_none, parse_object_id

if TYPE_CHECKING:
    from bson import ObjectId


@dataclass
class Student:
    """Document in the `students` collection."""

    prn: str
    branch_long: str
    branch_short: str
    campus: str
    year: str
    id: ObjectId | None = None

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> Self:
        return cls(
            id=parse_object_id(doc),
            prn=doc["prn"],
            branch_long=doc["branch_long"],
            branch_short=doc["branch_short"],
            campus=doc["campus"],
            year=doc["year"],
        )

    def to_document(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "prn": self.prn,
            "branch_long": self.branch_long,
            "branch_short": self.branch_short,
            "campus": self.campus,
            "year": self.year,
        }
        if self.id is not None:
            doc["_id"] = self.id
        return omit_none(doc)


class StudentStore(TypedCollection[Student]):
    """Store for the `students` collection."""

    model = Student
    field_map: ClassVar[dict[str, str]] = {
        "id": "_id",
        "prn": "prn",
        "branch_long": "branch_long",
        "branch_short": "branch_short",
        "campus": "campus",
        "year": "year",
    }
    indexes: ClassVar[list[IndexSpec]] = [
        ([("prn", 1)], {"unique": True, "name": "students_prn_key"}),
    ]

    async def upsert_by_prn(self, student: Student) -> None:
        """Create or update a student document keyed by PRN."""
        await self._collection.update_one(
            {"prn": student.prn},
            {
                "$set": {
                    "branch_long": student.branch_long,
                    "branch_short": student.branch_short,
                    "campus": student.campus,
                    "year": student.year,
                },
                "$setOnInsert": {
                    "prn": student.prn,
                },
            },
            upsert=True,
        )
