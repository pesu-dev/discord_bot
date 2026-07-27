"""Unit tests for typed Mongo document models and TypedCollection stores."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from bson import ObjectId

from src.data.mongo import (
    AnonBan,
    AnonBanStore,
    Branch,
    Campus,
    Link,
    LinkStore,
    Mute,
    MuteStore,
    Stores,
    Student,
    StudentStore,
)
from src.data.mongo._base import TypedCollection, omit_none, parse_object_id


def test_omit_none_and_parse_object_id() -> None:
    assert omit_none({"a": 1, "b": None, "c": 0}) == {"a": 1, "c": 0}
    oid = ObjectId()
    assert parse_object_id({}) is None
    assert parse_object_id({"_id": oid}) is oid
    assert parse_object_id({"_id": str(oid)}) == oid


def test_link_round_trip() -> None:
    oid = ObjectId()
    now = datetime.now(UTC)
    link = Link(id=oid, user_id="1", prn="PES1UG21CS001", linked_at=now, created_at=now, updated_at=now)
    doc = link.to_document()
    assert doc["userId"] == "1"
    assert doc["_id"] == oid
    restored = Link.from_document(doc)
    assert restored.user_id == "1"
    assert restored.prn == "PES1UG21CS001"
    assert restored.id == oid


def test_link_to_document_omits_none_id() -> None:
    link = Link(user_id="1", prn="x")
    doc = link.to_document()
    assert "_id" not in doc
    assert "linkedAt" not in doc


def test_student_round_trip() -> None:
    oid = ObjectId()
    student = Student(
        id=oid,
        prn="PES1UG21CS001",
        year="2021",
        branch=Branch(full="CSE Full", short="CSE"),
        campus=Campus(code=1, short="RR"),
        created_at=datetime.now(UTC),
    )
    doc = student.to_document()
    assert doc["branch"] == {"full": "CSE Full", "short": "CSE"}
    assert doc["campus"] == {"code": 1, "short": "RR"}
    restored = Student.from_document(doc)
    assert restored.branch.short == "CSE"
    assert restored.campus.code == 1
    assert restored.id == oid


def test_anonban_round_trip() -> None:
    oid = ObjectId()
    banned_at = datetime.now(UTC)
    ban = AnonBan(
        id=oid,
        user_id="9",
        reason="spam",
        banned_at=banned_at,
        active=True,
        expires_at=banned_at + timedelta(hours=1),
    )
    doc = ban.to_document()
    assert doc["userId"] == "9"
    assert doc["expiresAt"] is not None
    restored = AnonBan.from_document(doc)
    assert restored.reason == "spam"
    assert restored.active is True


def test_anonban_permanent_omits_expires() -> None:
    ban = AnonBan(
        user_id="9",
        reason="perm",
        banned_at=datetime.now(UTC),
        active=True,
        expires_at=None,
    )
    assert "expiresAt" not in ban.to_document()


def test_mute_round_trip() -> None:
    oid = ObjectId()
    now = datetime.now(UTC)
    mute = Mute(
        id=oid,
        user_id=1,
        channel_id=2,
        moderator_id=3,
        mute_time=now,
        unmute_time=now + timedelta(hours=1),
        reason="noise",
        active=True,
        is_self_mute=False,
        duration_seconds=3600,
        unmute_type="manual",
        unmuted_by=3,
    )
    doc = mute.to_document()
    restored = Mute.from_document(doc)
    assert restored.user_id == 1
    assert restored.unmuted_by == 3
    assert restored.duration_seconds == 3600


def test_mute_from_document_null_unmuted_by() -> None:
    now = datetime.now(UTC)
    mute = Mute.from_document(
        {
            "user_id": 1,
            "channel_id": 2,
            "moderator_id": 3,
            "mute_time": now,
            "unmute_time": now,
            "reason": "x",
            "active": True,
            "is_self_mute": False,
            "unmuted_by": None,
        }
    )
    assert mute.unmuted_by is None


class _FakeCursor:
    def __init__(self, docs: list[dict[str, Any]]) -> None:
        self._docs = docs

    def __aiter__(self) -> _FakeCursor:
        self._iter = iter(self._docs)
        return self

    async def __anext__(self) -> dict[str, Any]:
        try:
            return next(self._iter)
        except StopIteration as exc:
            raise StopAsyncIteration from exc

    async def to_list(self, length: int | None) -> list[dict[str, Any]]:
        return self._docs[:length] if length is not None else list(self._docs)


def _collection(docs: list[dict[str, Any]] | None = None) -> MagicMock:
    coll = MagicMock()
    docs = docs or []
    coll.find = MagicMock(return_value=_FakeCursor(docs))
    coll.find_one = AsyncMock(return_value=docs[0] if docs else None)
    coll.insert_one = AsyncMock(return_value=MagicMock(inserted_id=ObjectId()))
    coll.update_one = AsyncMock(return_value=MagicMock(modified_count=1))
    coll.update_many = AsyncMock(return_value=MagicMock(modified_count=1))
    coll.delete_one = AsyncMock(return_value=MagicMock(deleted_count=1))
    coll.find_one_and_update = AsyncMock(return_value=docs[0] if docs else None)
    return coll


async def test_typed_collection_crud() -> None:
    oid = ObjectId()
    now = datetime.now(UTC)
    doc = {
        "_id": oid,
        "userId": "1",
        "prn": "PES1UG21CS001",
        "linkedAt": now,
    }
    coll = _collection([doc])
    store = LinkStore(coll)

    found = await store.find_one(user_id="1")
    assert found is not None
    assert found.prn == "PES1UG21CS001"

    assert await store.exists(user_id="1") is True
    many = await store.find_many(user_id="1", limit=10)
    assert len(many) == 1

    results = [item async for item in store.find(user_id="1")]
    assert len(results) == 1

    empty = [item async for item in store.find()]
    assert len(empty) == 1

    await store.insert_one(Link(user_id="2", prn="x"))
    coll.insert_one.assert_awaited()

    await store.update_one(user_id="1", set_fields={"prn": "y"})
    coll.update_one.assert_awaited()

    await store.update_many(user_id="1", set_fields={"prn": "z"})
    coll.update_many.assert_awaited()

    await store.delete_one(user_id="1")
    coll.delete_one.assert_awaited()

    updated = await store.find_one_and_update(user_id="1", set_fields={"prn": "w"})
    assert updated is not None


async def test_student_upsert_by_prn() -> None:
    coll = _collection()
    coll.update_one = AsyncMock()
    store = StudentStore(coll)
    student = Student(
        prn="PES1UG21CS001",
        year="2021",
        branch=Branch(full="CSE Full", short="CSE"),
        campus=Campus(code=1, short="RR"),
    )
    await store.upsert_by_prn(student)
    coll.update_one.assert_awaited_once()
    args, kwargs = coll.update_one.await_args
    assert args[0] == {"prn": "PES1UG21CS001"}
    assert kwargs["upsert"] is True
    assert args[1]["$set"]["year"] == "2021"
    assert args[1]["$setOnInsert"]["prn"] == "PES1UG21CS001"


async def test_typed_collection_errors() -> None:
    store = LinkStore(_collection())
    with pytest.raises(TypeError, match="Unknown field"):
        await store.find_one(not_a_field=1)
    with pytest.raises(TypeError, match="At least one"):
        await store.find_one()
    with pytest.raises(TypeError, match="At least one"):
        await store.exists()


async def test_typed_collection_none_results() -> None:
    coll = _collection([])
    coll.find_one = AsyncMock(return_value=None)
    coll.find_one_and_update = AsyncMock(return_value=None)
    store = LinkStore(coll)
    assert await store.find_one(user_id="missing") is None
    assert await store.exists(user_id="missing") is False
    assert await store.find_one_and_update(user_id="missing", set_fields={"prn": "x"}) is None


async def test_anonban_store_helpers() -> None:
    oid = ObjectId()
    now = datetime.now(UTC)
    doc = {
        "_id": oid,
        "userId": "55",
        "reason": "spam",
        "bannedAt": now - timedelta(hours=2),
        "expiresAt": now - timedelta(seconds=1),
        "active": True,
    }
    coll = _collection([doc])
    store = AnonBanStore(coll)

    expired = [ban async for ban in store.find_expired(now)]
    assert len(expired) == 1
    assert expired[0].user_id == "55"

    result = await store.deactivate("55")
    assert result is not None
    coll.find_one_and_update.assert_awaited()


async def test_mute_store_helpers() -> None:
    oid = ObjectId()
    now = datetime.now(UTC)
    doc = {
        "_id": oid,
        "user_id": 50,
        "channel_id": 1,
        "moderator_id": 2,
        "mute_time": now - timedelta(hours=1),
        "unmute_time": now - timedelta(seconds=1),
        "reason": "x",
        "active": True,
        "is_self_mute": False,
    }
    coll = _collection([doc])
    store = MuteStore(coll)

    expired = await store.find_expired(now, limit=10)
    assert len(expired) == 1

    await store.mark_unmuted(oid, unmute_time=now, unmute_type="loop_auto", unmuted_by=2)
    coll.update_one.assert_awaited()

    await store.mark_unmuted(oid, unmute_time=now, unmute_type="auto_member_left")
    await store.deactivate_active(50, unmute_time=now, unmute_type="manual", unmuted_by=2)
    coll.update_many.assert_awaited()


async def test_student_store_and_stores_container() -> None:
    doc = {
        "_id": ObjectId(),
        "prn": "PES1UG21CS001",
        "year": "2021",
        "branch": {"full": "CSE", "short": "CSE"},
        "campus": {"code": 1, "short": "RR"},
    }
    coll = _collection([doc])
    store = StudentStore(coll)
    student = await store.find_one(prn="PES1UG21CS001")
    assert student is not None
    assert student.campus.short == "RR"

    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=lambda name: _collection())
    stores = Stores(db)
    assert isinstance(stores.links, LinkStore)
    assert isinstance(stores.students, StudentStore)
    assert isinstance(stores.anonbans, AnonBanStore)
    assert isinstance(stores.mutes, MuteStore)


async def test_typed_collection_unknown_field_on_set() -> None:
    class _Bad(TypedCollection[Link]):
        model = Link
        field_map = {"user_id": "userId"}

    store = _Bad(_collection())
    with pytest.raises(TypeError, match="Unknown field"):
        await store.update_one(user_id="1", set_fields={"prn": "x"})
