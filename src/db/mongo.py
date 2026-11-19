"""Connexion MongoDB + setup des collections médallion."""

from __future__ import annotations

from typing import Any

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.database import Database

from src.config import (
    COLLECTION_CLEANED_POSTS,
    COLLECTION_POSTS,
    COLLECTION_POSTS_ANALYSIS,
    MONGO_DB,
    MONGO_URI,
)

_client: MongoClient | None = None


def get_client(uri: str | None = None) -> MongoClient:
    global _client
    if _client is None:
        _client = MongoClient(uri or MONGO_URI, serverSelectionTimeoutMS=5000)
    return _client


def get_db(name: str | None = None) -> Database:
    return get_client()[name or MONGO_DB]


def get_posts_collection() -> Collection:
    """Bronze — posts bruts scrapés."""
    return get_db()[COLLECTION_POSTS]


def get_cleaned_posts_collection() -> Collection:
    """Silver — posts nettoyés / normalisés (étape suivante)."""
    return get_db()[COLLECTION_CLEANED_POSTS]


def get_posts_analysis_collection() -> Collection:
    """Gold — sentiment + thèmes Hugging Face (étape suivante)."""
    return get_db()[COLLECTION_POSTS_ANALYSIS]


def ensure_indexes() -> dict[str, Any]:
    """Crée les index bronze + silver + gold."""
    posts = get_posts_collection()
    posts.create_index(
        [("source", ASCENDING), ("source_post_id", ASCENDING)],
        unique=True,
        name="uniq_source_post",
    )
    posts.create_index([("scraped_at", ASCENDING)], name="idx_scraped_at")
    posts.create_index([("query", ASCENDING)], name="idx_query")
    posts.create_index([("lang", ASCENDING)], name="idx_lang")

    cleaned = get_cleaned_posts_collection()
    cleaned.create_index(
        [("source", ASCENDING), ("source_post_id", ASCENDING)],
        unique=True,
        name="uniq_source_cleaned_post",
    )
    cleaned.create_index([("cleaned_at", ASCENDING)], name="idx_cleaned_at")
    cleaned.create_index([("query", ASCENDING)], name="idx_cleaned_query")
    cleaned.create_index([("lang", ASCENDING)], name="idx_cleaned_lang")

    gold = get_posts_analysis_collection()
    gold.create_index(
        [("source", ASCENDING), ("source_post_id", ASCENDING)],
        unique=True,
        name="uniq_source_analysis",
    )
    gold.create_index([("analyzed_at", ASCENDING)], name="idx_analyzed_at")
    gold.create_index([("sentiment", ASCENDING)], name="idx_sentiment")
    gold.create_index([("query", ASCENDING)], name="idx_analysis_query")

    return {
        "db": MONGO_DB,
        "collections": {
            "bronze": COLLECTION_POSTS,
            "silver": COLLECTION_CLEANED_POSTS,
            "gold": COLLECTION_POSTS_ANALYSIS,
        },
        "indexes_posts": list(posts.list_indexes()),
        "indexes_cleaned_posts": list(cleaned.list_indexes()),
        "indexes_posts_analysis": list(gold.list_indexes()),
    }


def ping() -> dict[str, Any]:
    client = get_client()
    info = client.admin.command("ping")
    return {"ok": info.get("ok") == 1, "uri": MONGO_URI, "db": MONGO_DB}


def close() -> None:
    global _client
    if _client is not None:
        _client.close()
        _client = None
