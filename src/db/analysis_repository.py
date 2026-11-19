"""Repository gold : collection `posts_analysis`."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo import DESCENDING, UpdateOne
from pymongo.results import BulkWriteResult

from src.db.mongo import get_posts_analysis_collection


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(doc: dict[str, Any]) -> dict[str, Any]:
    out = dict(doc)
    if "_id" in out:
        out["id"] = str(out.pop("_id"))
    for key, value in list(out.items()):
        if isinstance(value, ObjectId):
            out[key] = str(value)
        elif isinstance(value, datetime):
            out[key] = value.isoformat()
    return out


def upsert_analyses(docs: list[dict[str, Any]]) -> BulkWriteResult:
    collection = get_posts_analysis_collection()
    ops: list[UpdateOne] = []

    for doc in docs:
        source = doc.get("source")
        source_post_id = doc.get("source_post_id")
        if not source or not source_post_id:
            raise ValueError("gold doc requires source + source_post_id")

        payload = {**doc, "analyzed_at": _now(), "layer": "gold"}
        ops.append(
            UpdateOne(
                {"source": source, "source_post_id": source_post_id},
                {
                    "$set": payload,
                    "$setOnInsert": {"inserted_at": _now()},
                },
                upsert=True,
            )
        )

    if not ops:
        raise ValueError("aucune analyse à upsert")

    return collection.bulk_write(ops, ordered=False)


def list_analyses(
    *,
    source: str | None = None,
    sentiment: str | None = None,
    query: str | None = None,
    limit: int = 20,
    skip: int = 0,
) -> dict[str, Any]:
    collection = get_posts_analysis_collection()
    filt: dict[str, Any] = {"layer": "gold"}
    if source:
        filt["source"] = source
    if sentiment:
        filt["sentiment"] = sentiment
    if query:
        filt["query"] = query

    limit = max(1, min(limit, 200))
    skip = max(0, skip)
    total = collection.count_documents(filt)
    cursor = (
        collection.find(filt)
        .sort("analyzed_at", DESCENDING)
        .skip(skip)
        .limit(limit)
    )
    items = [_serialize(doc) for doc in cursor]
    return {
        "total": total,
        "limit": limit,
        "skip": skip,
        "count": len(items),
        "items": items,
    }


def get_analysis(post_id: str) -> dict[str, Any] | None:
    collection = get_posts_analysis_collection()
    doc = None
    if ObjectId.is_valid(post_id):
        doc = collection.find_one({"_id": ObjectId(post_id)})
    if doc is None:
        doc = collection.find_one({"source_post_id": post_id})
    return _serialize(doc) if doc else None


def count_analyses(sentiment: str | None = None) -> int:
    filt: dict[str, Any] = {}
    if sentiment:
        filt["sentiment"] = sentiment
    return get_posts_analysis_collection().count_documents(filt)
