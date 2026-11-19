"""
Détection de thèmes — zero-shot multilingual
Modèle: MoritzLaurer/mDeBERTa-v3-base-mnli-xnli

Thèmes projet (cahier des charges) :
  solitude, soutien_psychologique, symptomes, anxiete, espoir_retablissement, ...
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Any

DEFAULT_MODEL = "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli"

# Labels zero-shot (anglais = plus stable pour NLI ; mapping FR en sortie)
DEFAULT_THEME_CANDIDATES = [
    "loneliness and social isolation",
    "psychological support and therapy",
    "depression symptoms",
    "anxiety and stress",
    "hope recovery and resilience",
    "suicidal thoughts or self harm",
    "medication and treatment",
    "family and relationships",
]

THEME_LABEL_MAP = {
    "loneliness and social isolation": "solitude",
    "psychological support and therapy": "soutien_psychologique",
    "depression symptoms": "symptomes",
    "anxiety and stress": "anxiete",
    "hope recovery and resilience": "espoir_retablissement",
    "suicidal thoughts or self harm": "ideations_suicidaires",
    "medication and treatment": "traitement_medical",
    "family and relationships": "famille_relations",
}


def _model_name() -> str:
    return os.getenv("HF_THEME_MODEL", DEFAULT_MODEL) or DEFAULT_MODEL


def _theme_candidates() -> list[str]:
    raw = os.getenv("HF_THEME_LABELS")
    if raw:
        return [x.strip() for x in raw.split("|") if x.strip()]
    return list(DEFAULT_THEME_CANDIDATES)


def _map_label(raw_label: str) -> str:
    return THEME_LABEL_MAP.get(raw_label, raw_label.replace(" ", "_").lower())


@lru_cache(maxsize=1)
def get_theme_pipeline():
    from transformers import pipeline

    token = os.getenv("HUGGINGFACE_TOKEN") or os.getenv("HF_TOKEN") or None
    kwargs: dict[str, Any] = {
        "task": "zero-shot-classification",
        "model": _model_name(),
    }
    if token:
        kwargs["token"] = token
    try:
        return pipeline(**kwargs, device=-1)
    except TypeError:
        kwargs.pop("token", None)
        return pipeline(**kwargs)


def predict_themes(
    text: str,
    *,
    top_k: int = 3,
    multi_label: bool = True,
    threshold: float = 0.35,
) -> dict[str, Any]:
    """
    Retourne les thèmes dominants + scores.
    multi_label=True : un post peut avoir plusieurs thèmes.
    """
    if not text or not text.strip():
        raise ValueError("texte vide")

    candidates = _theme_candidates()
    pipe = get_theme_pipeline()
    raw = pipe(
        text,
        candidate_labels=candidates,
        multi_label=multi_label,
        truncation=True,
    )

    labels = raw.get("labels") or []
    scores = raw.get("scores") or []
    ranked = [
        {
            "theme": _map_label(label),
            "label_raw": label,
            "score": round(float(score), 6),
        }
        for label, score in zip(labels, scores)
    ]

    selected = [item for item in ranked if item["score"] >= threshold][:top_k]
    if not selected and ranked:
        selected = ranked[:1]

    return {
        "dominant_theme": selected[0]["theme"] if selected else None,
        "themes": selected,
        "all_theme_scores": ranked,
        "theme_model": _model_name(),
        "theme_threshold": threshold,
    }


def predict_themes_batch(
    texts: list[str],
    *,
    top_k: int = 3,
    multi_label: bool = True,
    threshold: float = 0.35,
) -> list[dict[str, Any]]:
    return [
        predict_themes(t, top_k=top_k, multi_label=multi_label, threshold=threshold)
        for t in texts
    ]
