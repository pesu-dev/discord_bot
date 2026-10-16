from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, ClassVar, Self

from src.data.mongo._base import IndexSpec, TypedCollection, omit_none, parse_object_id

if TYPE_CHECKING:
    from datetime import datetime

    from bson import ObjectId


@dataclass
class GitLink:
    """Document in the `git_team` collection."""

    discord_user_id: str
    github_username: str
    github_user_id: int
    invited_at: datetime
    id: ObjectId | None = None

    @classmethod
    def from_document(cls, doc: dict[str, Any]) -> Self:
        return cls(
            id=parse_object_id(doc),
            discord_user_id=str(doc["discord_user_id"]),
            invited_at=doc["invited_at"],
            github_username=doc["github_username"],
            github_user_id=str(doc["github_user_id"]),
        )

    def to_document(self) -> dict[str, Any]:
        doc: dict[str, Any] = {
            "discord_user_id": self.discord_user_id,
            "invited_at": self.invited_at,
            "github_username": self.github_username,
            "github_user_id": self.github_user_id,
        }
        if self.id is not None:
            doc["_id"] = self.id
        return omit_none(doc)


class GitLinkStore(TypedCollection[GitLink]):
    """Store for the `git_links` collection."""

    model = GitLink
    field_map: ClassVar[dict[str, str]] = {
        "id": "_id",
        "discord_user_id": "discord_user_id",
        "github_username": "github_username",
        "github_user_id": "github_user_id",
        "invited_at": "invited_at",
    }
    indexes: ClassVar[list[IndexSpec]] = [
        ([("discord_user_id", 1)], {"unique": True, "name": "git_links_discord_user_id_key"}),
        ([("github_username", 1)], {"unique": True, "name": "git_links_github_username_key"}),
        ([("github_user_id", 1)], {"unique": True, "name": "git_links_github_user_id_key"}),
    ]
