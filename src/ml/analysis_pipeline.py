"""Silver → Gold : sentiment + thèmes → posts_analysis."""

from __future__ import annotations

from typing import Any

from src.db.analysis_repository import get_analysis, upsert_analyses
from src.db.cleaned_posts_repository import get_cleaned_post, list_cleaned_posts
from src.ml.sentiment_classifier import predict_sentiment, predict_sentiment_batch
from src.ml.theme_detector import predict_themes, predict_themes_batch


def silver_to_gold_doc(
    silver: dict[str, Any],
    sentiment_pred: dict[str, Any],
    theme_pred: dict[str, Any] | None = None,
) -> dict[str, Any]:
    doc = {
        "source": silver.get("source"),
        "source_post_id": silver.get("source_post_id"),
        "silver_id": silver.get("id"),
        "bronze_id": silver.get("bronze_id"),
        "layer": "gold",
        "query": silver.get("query"),
        "lang": silver.get("lang"),
        "cleaned_text": silver.get("cleaned_text"),
        "author": silver.get("author") or {},
        "url": silver.get("url"),
        # sentiment (3 classes projet)
        "sentiment": sentiment_pred["sentiment"],
        "confidence": sentiment_pred["confidence"],
        "sentiment_scores": sentiment_pred["sentiment_scores"],
        "fine_label": sentiment_pred["fine_label"],
        "fine_confidence": sentiment_pred["fine_confidence"],
        "fine_scores": sentiment_pred["fine_scores"],
        "sentiment_model": sentiment_pred["model"],
        # thèmes
        "themes": None,
        "dominant_theme": None,
        "theme_model": None,
    }
    if theme_pred:
        doc["themes"] = theme_pred.get("themes")
        doc["dominant_theme"] = theme_pred.get("dominant_theme")
        doc["all_theme_scores"] = theme_pred.get("all_theme_scores")
        doc["theme_model"] = theme_pred.get("theme_model")
        doc["theme_threshold"] = theme_pred.get("theme_threshold")
    return doc


def analyze_text(
    text: str,
    *,
    with_themes: bool = True,
) -> dict[str, Any]:
    """Preview sentiment (+ thèmes) sans écriture Mongo."""
    out = {"sentiment": predict_sentiment(text)}
    if with_themes:
        out["themes"] = predict_themes(text)
    return out


def analyze_silver_batch(
    *,
    source: str | None = None,
    lang: str | None = None,
    query: str | None = None,
    limit: int = 20,
    skip: int = 0,
    with_themes: bool = True,
) -> dict[str, Any]:
    """Lit silver, prédit sentiment (+ thèmes), upsert gold."""
    page = list_cleaned_posts(
        source=source,
        lang=lang,
        query=query,
        limit=limit,
        skip=skip,
    )
    items = page["items"]
    if not items:
        return {
            "silver_read": 0,
            "silver_total_matching": page["total"],
            "gold_written": 0,
            "skipped_empty": 0,
            "mongo": {"upserted": 0, "modified": 0, "matched": 0},
            "sample": [],
        }

    texts: list[str] = []
    keep_silver: list[dict[str, Any]] = []
    skipped_empty = 0
    for silver in items:
        text = (silver.get("cleaned_text") or "").strip()
        if not text:
            skipped_empty += 1
            continue
        texts.append(text)
        keep_silver.append(silver)

    sentiment_preds = predict_sentiment_batch(texts) if texts else []
    theme_preds: list[dict[str, Any] | None]
    if with_themes and texts:
        theme_preds = predict_themes_batch(texts)
    else:
        theme_preds = [None] * len(texts)

    gold_docs = [
        silver_to_gold_doc(silver, sent, theme)
        for silver, sent, theme in zip(keep_silver, sentiment_preds, theme_preds)
    ]

    write_stats = {"upserted": 0, "modified": 0, "matched": 0}
    if gold_docs:
        result = upsert_analyses(gold_docs)
        write_stats = {
            "upserted": result.upserted_count,
            "modified": result.modified_count,
            "matched": result.matched_count,
        }

    return {
        "silver_read": page["count"],
        "silver_total_matching": page["total"],
        "gold_written": len(gold_docs),
        "skipped_empty": skipped_empty,
        "mongo": write_stats,
        "sample": gold_docs[:3],
    }


def analyze_silver_by_id(
    post_id: str,
    *,
    with_themes: bool = True,
) -> dict[str, Any] | None:
    silver = get_cleaned_post(post_id)
    if not silver:
        return None
    text = (silver.get("cleaned_text") or "").strip()
    if not text:
        return None

    sentiment_pred = predict_sentiment(text)
    theme_pred = predict_themes(text) if with_themes else None
    doc = silver_to_gold_doc(silver, sentiment_pred, theme_pred)
    upsert_analyses([doc])
    return get_analysis(doc["source_post_id"]) or doc
