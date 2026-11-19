"""
Sentiment analysis — tabularisai/multilingual-sentiment-analysis

Modèle 5 classes :
  Very Negative | Negative | Neutral | Positive | Very Positive

Mapping projet (positif / négatif / neutre) :
  Very Negative + Negative → negative
  Neutral                  → neutral
  Positive + Very Positive → positive
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

DEFAULT_MODEL = "tabularisai/multilingual-sentiment-analysis"

# Labels bruts du modèle (index 0..4)
FINE_LABELS = {
    0: "Very Negative",
    1: "Negative",
    2: "Neutral",
    3: "Positive",
    4: "Very Positive",
}

# Mapping → 3 classes projet
FINE_TO_SENTIMENT = {
    "Very Negative": "negative",
    "Negative": "negative",
    "Neutral": "neutral",
    "Positive": "positive",
    "Very Positive": "positive",
    # variantes éventuelles du pipeline
    "LABEL_0": "negative",
    "LABEL_1": "negative",
    "LABEL_2": "neutral",
    "LABEL_3": "positive",
    "LABEL_4": "positive",
}


def _model_name() -> str:
    return os.getenv("HF_SENTIMENT_MODEL", DEFAULT_MODEL)


@lru_cache(maxsize=1)
def get_pipeline():
    """Charge le pipeline HF une seule fois (lazy)."""
    from transformers import pipeline

    token = os.getenv("HUGGINGFACE_TOKEN") or os.getenv("HF_TOKEN") or None
    kwargs: dict[str, Any] = {
        "task": "text-classification",
        "model": _model_name(),
        "top_k": None,  # toutes les classes
        "truncation": True,
        "max_length": 512,
    }
    if token:
        kwargs["token"] = token

    # CPU par défaut (Docker / machines sans GPU)
    try:
        return pipeline(**kwargs, device=-1)
    except TypeError:
        # anciennes versions transformers
        kwargs.pop("token", None)
        return pipeline(**kwargs)


def map_fine_label(fine_label: str) -> str:
    label = (fine_label or "").strip()
    mapped = FINE_TO_SENTIMENT.get(label)
    if mapped:
        return mapped
    # fallback case-insensitive
    for key, value in FINE_TO_SENTIMENT.items():
        if key.lower() == label.lower():
            return value
    return "neutral"


def _scores_dict(raw_scores: list[dict[str, Any]]) -> dict[str, float]:
    return {item["label"]: float(item["score"]) for item in raw_scores}


def _aggregate_sentiment_scores(fine_scores: dict[str, float]) -> dict[str, float]:
    """Somme des scores very_* dans negative / positive."""
    agg = {"negative": 0.0, "neutral": 0.0, "positive": 0.0}
    for fine, score in fine_scores.items():
        bucket = map_fine_label(fine)
        agg[bucket] = agg.get(bucket, 0.0) + float(score)
    return agg


def predict_sentiment(text: str) -> dict[str, Any]:
    """Prédit le sentiment d'un texte (silver cleaned_text)."""
    if not text or not text.strip():
        raise ValueError("texte vide")

    pipe = get_pipeline()
    raw = pipe(text)
    # pipeline top_k=None → list[list[{label, score}]] ou list[{label, score}]
    if raw and isinstance(raw[0], list):
        scores_list = raw[0]
    else:
        scores_list = raw

    fine_scores = _scores_dict(scores_list)
    fine_label = max(fine_scores, key=fine_scores.get)
    fine_confidence = fine_scores[fine_label]

    sentiment_scores = _aggregate_sentiment_scores(fine_scores)
    sentiment = max(sentiment_scores, key=sentiment_scores.get)
    confidence = sentiment_scores[sentiment]

    return {
        "sentiment": sentiment,  # negative | neutral | positive
        "confidence": round(confidence, 6),
        "fine_label": fine_label,  # 5 classes brutes
        "fine_confidence": round(fine_confidence, 6),
        "fine_scores": {k: round(v, 6) for k, v in fine_scores.items()},
        "sentiment_scores": {k: round(v, 6) for k, v in sentiment_scores.items()},
        "model": _model_name(),
    }


def predict_sentiment_batch(texts: list[str]) -> list[dict[str, Any]]:
    """Batch prediction (liste de textes)."""
    if not texts:
        return []
    pipe = get_pipeline()
    raw_batch = pipe(texts)
    results: list[dict[str, Any]] = []

    for raw in raw_batch:
        scores_list = raw if isinstance(raw, list) and raw and isinstance(raw[0], dict) else raw
        # Si un seul dict (top_k=1), wrap
        if isinstance(scores_list, dict):
            scores_list = [scores_list]

        fine_scores = _scores_dict(scores_list)
        fine_label = max(fine_scores, key=fine_scores.get)
        fine_confidence = fine_scores[fine_label]
        sentiment_scores = _aggregate_sentiment_scores(fine_scores)
        sentiment = max(sentiment_scores, key=sentiment_scores.get)

        results.append(
            {
                "sentiment": sentiment,
                "confidence": round(sentiment_scores[sentiment], 6),
                "fine_label": fine_label,
                "fine_confidence": round(fine_confidence, 6),
                "fine_scores": {k: round(v, 6) for k, v in fine_scores.items()},
                "sentiment_scores": {
                    k: round(v, 6) for k, v in sentiment_scores.items()
                },
                "model": _model_name(),
            }
        )
    return results
