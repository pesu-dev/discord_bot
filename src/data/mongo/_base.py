"""Shared Mongo document helpers and typed collection wrappers."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any, ClassVar

from bson import ObjectId
from pymongo import ReplaceOne

if TYPE_CHECKING:
    from collections.abc import AsyncIterator, Mapping

    from pymongo.asynchronous.collection import AsyncCollection
    from pymongo.results import DeleteResult, InsertOneResult, UpdateResult

IndexKeys = Sequence[tuple[str, int]]
IndexSpec = tuple[IndexKeys, dict[str, Any]]


def omit_none(doc: dict[str, Any]) -> dict[str, Any]:
    """Drop keys whose value is None (insert-safe optional fields)."""
    return {key: value for key, value in doc.items() if value is not None}


def parse_object_id(doc: dict[str, Any]) -> ObjectId | None:
    """Extract `_id` from a raw Mongo document, if present."""
    value = doc.get("_id")
    if value is None:
        return None
    if isinstance(value, ObjectId):
        return value
    return ObjectId(value)


class TypedCollection[ModelT]:
    """Equality-filter CRUD wrapper that maps snake_case fields to Mongo keys."""

    model: type[ModelT]
    field_map: ClassVar[dict[str, str]]
    indexes: ClassVar[list[IndexSpec]] = []
    # When True, Stores also binds ``archive.<name>`` with the same store class.
    # Overridden to False on archive twin instances.
    has_archive: bool = False

    def __init__(self, collection: AsyncCollection) -> None:
        self._collection = collection
        # Set by Stores._bind when ``has_archive`` is True on the hot store.
        self.archive: TypedCollection[Any] | None = None

    @property
    def name(self) -> str:
        """Underlying MongoDB collection name."""
        return self._collection.name

    def _mongo_key(self, field: str) -> str:
        try:
            return self.field_map[field]
        except KeyError as exc:
            msg = f"Unknown field {field!r} for {self.model.__name__}; expected one of {sorted(self.field_map)}"
            raise TypeError(msg) from exc

    def _to_mongo(self, fields: Mapping[str, object]) -> dict[str, object]:
        return {self._mongo_key(key): value for key, value in fields.items()}

    def _require_eq(self, eq: Mapping[str, object]) -> dict[str, object]:
        if not eq:
            msg = "At least one equality filter field is required"
            raise TypeError(msg)
        return self._to_mongo(eq)

    async def ensure_indexes(self) -> None:
        """Create declared indexes (idempotent when name/keys match)."""
        for keys, options in self.indexes:
            await self._collection.create_index(list(keys), **options)

    async def replace_upsert_into(
        self,
        dest: TypedCollection[Any],
        *,
        batch_size: int = 500,
    ) -> int:
        """Copy every document into ``dest``, replacing by ``_id`` (upsert).

        Returns the number of documents written. Bodies are copied as raw BSON
        so archive collections stay byte-identical to the hot source.
        """
        ops: list[ReplaceOne] = []
        written = 0

        async for doc in self._collection.find({}):
            ops.append(ReplaceOne({"_id": doc["_id"]}, doc, upsert=True))
            if len(ops) >= batch_size:
                await dest._collection.bulk_write(list(ops), ordered=False)
                written += len(ops)
                ops.clear()

        if ops:
            await dest._collection.bulk_write(list(ops), ordered=False)
            written += len(ops)

        return written

    async def find(self, **eq: object) -> AsyncIterator[ModelT]:
        query = self._to_mongo(eq) if eq else {}
        async for doc in self._collection.find(query):
            yield self.model.from_document(doc)  # type: ignore[attr-defined]

    async def find_one(self, **eq: object) -> ModelT | None:
        doc = await self._collection.find_one(self._require_eq(eq))
        if doc is None:
            return None
        return self.model.from_document(doc)  # type: ignore[attr-defined]

    async def exists(self, **eq: object) -> bool:
        """Return whether any document matches the equality filter."""
        doc = await self._collection.find_one(self._require_eq(eq), projection={"_id": 1})
        return doc is not None

    async def find_many(self, *, limit: int | None = None, **eq: object) -> list[ModelT]:
        query = self._to_mongo(eq) if eq else {}
        cursor = self._collection.find(query)
        docs = await cursor.to_list(length=limit)
        return [self.model.from_document(doc) for doc in docs]  # type: ignore[attr-defined]

    async def insert_one(self, model: ModelT) -> InsertOneResult:
        return await self._collection.insert_one(model.to_document())  # type: ignore[attr-defined]

    async def update_one(self, *, set_fields: Mapping[str, object], **eq: object) -> UpdateResult:
        return await self._collection.update_one(
            self._require_eq(eq),
            {"$set": self._to_mongo(set_fields)},
        )

    async def update_many(self, *, set_fields: Mapping[str, object], **eq: object) -> UpdateResult:
        return await self._collection.update_many(
            self._require_eq(eq),
            {"$set": self._to_mongo(set_fields)},
        )

    async def delete_one(self, **eq: object) -> DeleteResult:
        return await self._collection.delete_one(self._require_eq(eq))

    async def find_one_and_update(self, *, set_fields: Mapping[str, object], **eq: object) -> ModelT | None:
        doc = await self._collection.find_one_and_update(
            self._require_eq(eq),
            {"$set": self._to_mongo(set_fields)},
        )
        if doc is None:
            return None
        return self.model.from_document(doc)  # type: ignore[attr-defined]
