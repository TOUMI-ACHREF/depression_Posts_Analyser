"""Bronze → Silver : clean + upsert dans `cleaned_posts`."""

from __future__ import annotations

from typing import Any

from src.cleaner.text_cleaner import CLEANER_VERSION, clean_text
from src.db.cleaned_posts_repository import upsert_cleaned_posts
from src.db.posts_repository import get_bronze_post, list_bronze_posts


def bronze_to_silver_doc(bronze: dict[str, Any], *, lowercase: bool = True) -> dict[str, Any] | None:
    original = bronze.get("text") or ""
    cleaned = clean_text(original, lowercase=lowercase)
    if not cleaned:
        return None

    return {
        "source": bronze.get("source"),
        "source_post_id": bronze.get("source_post_id"),
        "bronze_id": bronze.get("id"),
        "layer": "silver",
        "query": bronze.get("query"),
        "lang": bronze.get("lang"),
        "original_text": original,
        "cleaned_text": cleaned,
        "author": bronze.get("author") or {},
        "created_at": bronze.get("created_at"),
        "url": bronze.get("url"),
        "cleaner_version": CLEANER_VERSION,
    }


def clean_bronze_batch(
    *,
    source: str | None = None,
    lang: str | None = None,
    query: str | None = None,
    limit: int = 50,
    skip: int = 0,
    lowercase: bool = True,
) -> dict[str, Any]:
    """Lit des posts bronze, clean, écrit silver."""
    page = list_bronze_posts(
        source=source,
        lang=lang,
        query=query,
        limit=limit,
        skip=skip,
        include_raw=False,
    )
    silver_docs: list[dict[str, Any]] = []
    skipped_empty = 0

    for bronze in page["items"]:
        doc = bronze_to_silver_doc(bronze, lowercase=lowercase)
        if doc is None:
            skipped_empty += 1
            continue
        silver_docs.append(doc)

    write_stats = {"upserted": 0, "modified": 0, "matched": 0}
    if silver_docs:
        result = upsert_cleaned_posts(silver_docs)
        write_stats = {
            "upserted": result.upserted_count,
            "modified": result.modified_count,
            "matched": result.matched_count,
        }

    return {
        "bronze_read": page["count"],
        "bronze_total_matching": page["total"],
        "silver_written": len(silver_docs),
        "skipped_empty_after_clean": skipped_empty,
        "mongo": write_stats,
        "cleaner_version": CLEANER_VERSION,
    }


def clean_bronze_by_id(post_id: str, *, lowercase: bool = True) -> dict[str, Any] | None:
    bronze = get_bronze_post(post_id, include_raw=False)
    if not bronze:
        return None
    doc = bronze_to_silver_doc(bronze, lowercase=lowercase)
    if not doc:
        return None
    upsert_cleaned_posts([doc])
    return doc
