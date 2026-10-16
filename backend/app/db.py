"""MongoDB access plus small helpers for IDs, counters and JSON output."""
from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from typing import Any

from pymongo import ReturnDocument

from .settings import settings

_client = None


def get_client():
    global _client
    if _client is None:
        if settings.use_mock_db:
            from mongomock_motor import AsyncMongoMockClient

            _client = AsyncMongoMockClient(tz_aware=True)
        else:
            from motor.motor_asyncio import AsyncIOMotorClient

            _client = AsyncIOMotorClient(settings.mongo_url, tz_aware=True, serverSelectionTimeoutMS=5000)
    return _client


def get_db():
    return get_client()[settings.mongo_db]


def reset_client() -> None:
    """Used by tests to start from an empty in-memory database."""
    global _client
    _client = None


def new_id() -> str:
    return uuid.uuid4().hex


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def next_number(db, name: str) -> int:
    doc = await db.counters.find_one_and_update(
        {"_id": name}, {"$inc": {"value": 1}}, upsert=True, return_document=ReturnDocument.AFTER
    )
    return int(doc["value"])


def _clean(value: Any) -> Any:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {k: _clean(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_clean(v) for v in value]
    return value


def out(doc: dict | None) -> dict | None:
    """Convert a Mongo document to JSON-friendly output with `id` instead of `_id`."""
    if doc is None:
        return None
    doc = dict(doc)
    doc["id"] = doc.pop("_id")
    return _clean(doc)


async def ensure_indexes(db) -> None:
    await db.violations.create_index("event_id", unique=True)
    await db.violations.create_index([("status", 1), ("detected_at", -1)])
    await db.violations.create_index("citizen_id")
    await db.challans.create_index("violation_id", unique=True)
    await db.citizens.create_index("citizen_ref", unique=True)
    await db.jobs.create_index([("status", 1), ("created_at", 1)])
