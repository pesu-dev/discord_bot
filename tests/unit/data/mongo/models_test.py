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
    AnonMute,
    AnonMuteStore,
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
    link = Link(id=oid, discord_user_id="1", prn="PES1UG21CS001", linked_at=now)
    doc = link.to_document()
    assert doc["discord_user_id"] == "1"
    assert doc["_id"] == oid
    restored = Link.from_document(doc)
    assert restored.discord_user_id == "1"
    assert restored.prn == "PES1UG21CS001"
    assert restored.id == oid


def test_link_to_document_omits_none_id() -> None:
    link = Link(discord_user_id="1", prn="x")
    doc = link.to_document()
    assert "_id" not in doc
    assert "linked_at" not in doc


def test_student_round_trip() -> None:
    oid = ObjectId()
    student = Student(
        id=oid,
        prn="PES1UG21CS001",
        year="2021",
        branch_long="CSE Full",
        branch_short="CSE",
        campus="RR",
    )
    doc = student.to_document()
    assert doc["branch_long"] == "CSE Full"
    assert doc["branch_short"] == "CSE"
    assert doc["campus"] == "RR"
    restored = Student.from_document(doc)
    assert restored.branch_short == "CSE"
    assert restored.campus == "RR"
    assert restored.id == oid


def test_student_to_document_omits_none_id() -> None:
    student = Student(
        prn="PES1UG21CS001",
        year="2021",
        branch_long="CSE Full",
        branch_short="CSE",
        campus="RR",
    )
    doc = student.to_document()
    assert "_id" not in doc


def test_anonban_round_trip() -> None:
    oid = ObjectId()
    banned_at = datetime.now(UTC)
    ban = AnonBan(
        id=oid,
        discord_user_id="9",
        reason="spam",
        banned_at=banned_at,
    )
    doc = ban.to_document()
    assert doc["discord_user_id"] == "9"
    assert "unbanned_at" not in doc
    restored = AnonBan.from_document(doc)
    assert restored.reason == "spam"
    assert restored.unbanned_at is None


def test_anonban_unbanned_round_trip() -> None:
    now = datetime.now(UTC)
    ban = AnonBan(
        discord_user_id="9",
        reason="perm",
        banned_at=now,
        unbanned_at=now,
    )
    assert ban.to_document()["unbanned_at"] == now


def test_mute_round_trip() -> None:
    oid = ObjectId()
    now = datetime.now(UTC)
    mute = Mute(
        id=oid,
        discord_user_id="1",
        discord_channel_id=2,
        moderator_discord_user_id="3",
        mute_time=now,
        original_unmute_time=now + timedelta(hours=1),
        reason="noise",
        unmuted_at=now + timedelta(minutes=30),
    )
    doc = mute.to_document()
    restored = Mute.from_document(doc)
    assert restored.discord_user_id == "1"
    assert restored.unmuted_at is not None
    assert restored.original_unmute_time == now + timedelta(hours=1)


def test_mute_to_document_omits_none_id() -> None:
    now = datetime.now(UTC)
    mute = Mute(
        discord_user_id="1",
        discord_channel_id=2,
        moderator_discord_user_id="3",
        mute_time=now,
        original_unmute_time=now,
        reason="x",
    )
    doc = mute.to_document()
    assert "_id" not in doc
    assert "unmuted_at" not in doc


def test_anon_mute_round_trip() -> None:
    oid = ObjectId()
    now = datetime.now(UTC)
    mute = AnonMute(
        id=oid,
        discord_user_id="1",
        moderator_discord_user_id="2",
        muted_at=now,
        original_unmute_time=now + timedelta(hours=1),
        reason="spam",
    )
    doc = mute.to_document()
    assert doc["_id"] == oid
    restored = AnonMute.from_document(doc)
    assert restored.discord_user_id == "1"
    assert restored.unmuted_at is None


def test_anon_mute_to_document_omits_none_id() -> None:
    now = datetime.now(UTC)
    mute = AnonMute(
        discord_user_id="1",
        moderator_discord_user_id="2",
        muted_at=now,
        original_unmute_time=now,
        reason="x",
    )
    doc = mute.to_document()
    assert "_id" not in doc
    assert "unmuted_at" not in doc


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
    coll.delete_many = AsyncMock(return_value=MagicMock(deleted_count=1))
    coll.find_one_and_update = AsyncMock(return_value=docs[0] if docs else None)
    coll.create_index = AsyncMock(return_value="idx")
    return coll


async def test_typed_collection_crud() -> None:
    oid = ObjectId()
    now = datetime.now(UTC)
    doc = {
        "_id": oid,
        "discord_user_id": "1",
        "prn": "PES1UG21CS001",
        "linked_at": now,
    }
    coll = _collection([doc])
    store = LinkStore(coll)

    found = await store.find_one(discord_user_id="1")
    assert found is not None
    assert found.prn == "PES1UG21CS001"

    assert await store.exists(discord_user_id="1") is True
    many = await store.find_many(discord_user_id="1", limit=10)
    assert len(many) == 1

    results = [item async for item in store.find(discord_user_id="1")]
    assert len(results) == 1

    empty = [item async for item in store.find()]
    assert len(empty) == 1

    await store.insert_one(Link(discord_user_id="2", prn="x"))
    coll.insert_one.assert_awaited()

    await store.update_one(discord_user_id="1", set_fields={"prn": "y"})
    coll.update_one.assert_awaited()

    await store.update_many(discord_user_id="1", set_fields={"prn": "z"})
    coll.update_many.assert_awaited()

    await store.delete_one(discord_user_id="1")
    coll.delete_one.assert_awaited()

    updated = await store.find_one_and_update(discord_user_id="1", set_fields={"prn": "w"})
    assert updated is not None


async def test_student_upsert_by_prn() -> None:
    coll = _collection()
    coll.update_one = AsyncMock()
    store = StudentStore(coll)
    student = Student(
        prn="PES1UG21CS001",
        year="2021",
        branch_long="CSE Full",
        branch_short="CSE",
        campus="RR",
    )
    await store.upsert_by_prn(student)
    coll.update_one.assert_awaited_once()
    args, kwargs = coll.update_one.await_args
    assert args[0] == {"prn": "PES1UG21CS001"}
    assert kwargs["upsert"] is True
    assert args[1]["$set"]["year"] == "2021"
    assert args[1]["$set"]["campus"] == "RR"
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
    assert await store.find_one(discord_user_id="999") is None
    assert await store.exists(discord_user_id="999") is False
    assert await store.find_one_and_update(discord_user_id="999", set_fields={"prn": "x"}) is None


async def test_anonban_store_helpers() -> None:
    oid = ObjectId()
    now = datetime.now(UTC)
    doc = {
        "_id": oid,
        "discord_user_id": "55",
        "reason": "spam",
        "banned_at": now - timedelta(hours=2),
    }
    coll = _collection([doc])
    store = AnonBanStore(coll)

    assert await store.has_active("55") is True
    active = await store.find_active("55")
    assert active is not None
    assert active.discord_user_id == "55"
    result = await store.unban("55", unbanned_at=now)
    assert result is not None
    coll.find_one_and_update.assert_awaited()

    await store.delete_stale(now)
    coll.delete_many.assert_awaited()


async def test_mute_store_helpers() -> None:
    oid = ObjectId()
    now = datetime.now(UTC)
    doc = {
        "_id": oid,
        "discord_user_id": "50",
        "discord_channel_id": 1,
        "moderator_discord_user_id": "2",
        "mute_time": now - timedelta(hours=1),
        "original_unmute_time": now - timedelta(seconds=1),
        "reason": "x",
    }
    coll = _collection([doc])
    store = MuteStore(coll)

    expired = await store.find_expired(now, limit=10)
    assert len(expired) == 1

    await store.mark_unmuted(oid, unmuted_at=now)
    coll.update_one.assert_awaited()

    await store.unmute_user("50", unmuted_at=now)
    coll.update_many.assert_awaited()

    await store.delete_stale(now)
    coll.delete_many.assert_awaited()


async def test_anon_mute_store_helpers() -> None:
    oid = ObjectId()
    now = datetime.now(UTC)
    doc = {
        "_id": oid,
        "discord_user_id": "50",
        "moderator_discord_user_id": "2",
        "muted_at": now - timedelta(hours=1),
        "original_unmute_time": now - timedelta(seconds=1),
        "reason": "x",
    }
    coll = _collection([doc])
    store = AnonMuteStore(coll)
    expired = await store.find_expired(now, limit=10)
    assert len(expired) == 1
    assert await store.has_active("50") is True
    active = await store.find_active("50")
    assert active is not None
    assert active.discord_user_id == "50"

    await store.mark_unmuted(oid, unmuted_at=now)
    coll.update_one.assert_awaited()

    await store.unmute_user("50", unmuted_at=now)
    coll.update_many.assert_awaited()

    await store.delete_stale(now)
    coll.delete_many.assert_awaited()


async def test_student_store_and_stores_container() -> None:
    doc = {
        "_id": ObjectId(),
        "prn": "PES1UG21CS001",
        "year": "2021",
        "branch_long": "CSE",
        "branch_short": "CSE",
        "campus": "RR",
    }
    coll = _collection([doc])
    store = StudentStore(coll)
    student = await store.find_one(prn="PES1UG21CS001")
    assert student is not None
    assert student.campus == "RR"

    db = MagicMock()
    db.__getitem__ = MagicMock(side_effect=lambda name: _collection())
    stores = await Stores.create(db)
    assert isinstance(stores.links, LinkStore)
    assert isinstance(stores.students, StudentStore)
    assert isinstance(stores.anon_bans, AnonBanStore)
    assert isinstance(stores.anon_mutes, AnonMuteStore)
    assert isinstance(stores.mutes, MuteStore)


async def test_store_index_specs() -> None:
    assert LinkStore.indexes[0][1]["unique"] is True
    assert StudentStore.indexes[0][1]["name"] == "students_prn_key"
    assert any(spec[1]["name"].startswith("mutes_") for spec in MuteStore.indexes)
    assert any(spec[1]["name"].startswith("anon_mutes_") for spec in AnonMuteStore.indexes)


async def test_typed_collection_unknown_field_on_set() -> None:
    class _Bad(TypedCollection[Link]):
        model = Link
        field_map = {"discord_user_id": "discord_user_id"}

    store = _Bad(_collection())
    with pytest.raises(TypeError, match="Unknown field"):
        await store.update_one(discord_user_id="1", set_fields={"prn": "x"})
