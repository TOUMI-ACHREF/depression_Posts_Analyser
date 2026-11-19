"""Repository bronze : collection `posts`."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo import DESCENDING, UpdateOne
from pymongo.results import BulkWriteResult

from src.db.mongo import ensure_indexes, get_posts_collection


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _serialize(doc: dict[str, Any]) -> dict[str, Any]:
    """Convertit ObjectId / datetime pour JSON API."""
    out = dict(doc)
    if "_id" in out:
        out["id"] = str(out.pop("_id"))
    for key, value in list(out.items()):
        if isinstance(value, ObjectId):
            out[key] = str(value)
        elif isinstance(value, datetime):
            out[key] = value.isoformat()
    return out


def to_bronze_document(post: dict[str, Any], *, query: str, source: str = "twitter") -> dict[str, Any]:
    """
    Document bronze (raw).
    text_clean ici = filtre qualité scrape (pas le nettoyage silver).
    """
    source_post_id = str(post.get("id") or post.get("source_post_id") or "")
    if not source_post_id:
        raise ValueError("post sans id / source_post_id")

    return {
        "source": source,
        "source_post_id": source_post_id,
        "layer": "bronze",
        "query": query,
        "text": post.get("text"),
        "text_clean": post.get("text_clean"),
        "lang": post.get("lang"),
        "created_at": post.get("created_at"),
        "scraped_at": _now(),
        "author": post.get("author") or {},
        "metrics": {
            "like_count": post.get("like_count"),
            "retweet_count": post.get("retweet_count"),
            "reply_count": post.get("reply_count"),
            "view_count": post.get("view_count"),
        },
        "hashtags": post.get("hashtags") or [],
        "urls": post.get("urls") or [],
        "url": post.get("url"),
        "raw": post,
    }


def upsert_posts(posts: list[dict[str, Any]], *, query: str, source: str = "twitter") -> BulkWriteResult:
    """Insert/update des posts bronze (dédupliqués sur source + source_post_id)."""
    ensure_indexes()
    collection = get_posts_collection()
    ops: list[UpdateOne] = []

    for post in posts:
        doc = to_bronze_document(post, query=query, source=source)
        ops.append(
            UpdateOne(
                {"source": doc["source"], "source_post_id": doc["source_post_id"]},
                {
                    "$set": doc,
                    "$setOnInsert": {"inserted_at": _now()},
                },
                upsert=True,
            )
        )

    if not ops:
        raise ValueError("aucun post à upsert")

    return collection.bulk_write(ops, ordered=False)


def count_posts(source: str | None = None) -> int:
    collection = get_posts_collection()
    filt: dict[str, Any] = {}
    if source:
        filt["source"] = source
    return collection.count_documents(filt)


def list_bronze_posts(
    *,
    source: str | None = None,
    lang: str | None = None,
    query: str | None = None,
    limit: int = 20,
    skip: int = 0,
    include_raw: bool = False,
) -> dict[str, Any]:
    """Liste paginée des posts bronze pour l'API."""
    collection = get_posts_collection()
    filt: dict[str, Any] = {"layer": "bronze"}
    if source:
        filt["source"] = source
    if lang:
        filt["lang"] = lang
    if query:
        filt["query"] = query

    limit = max(1, min(limit, 200))
    skip = max(0, skip)
    total = collection.count_documents(filt)

    projection = None if include_raw else {"raw": 0}
    cursor = (
        collection.find(filt, projection)
        .sort("scraped_at", DESCENDING)
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


def get_bronze_post(post_id: str, *, include_raw: bool = False) -> dict[str, Any] | None:
    """Récupère un post bronze par Mongo _id ou source_post_id."""
    collection = get_posts_collection()
    projection = None if include_raw else {"raw": 0}

    doc = None
    if ObjectId.is_valid(post_id):
        doc = collection.find_one({"_id": ObjectId(post_id)}, projection)
    if doc is None:
        doc = collection.find_one({"source_post_id": post_id}, projection)
    return _serialize(doc) if doc else None
