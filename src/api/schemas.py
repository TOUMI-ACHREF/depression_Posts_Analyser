"""Schémas Pydantic (réponses API) — modèles concrets pour OpenAPI/Swagger."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class AuthorSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    id: str | None = None
    username: str | None = None
    name: str | None = None


class MetricsSchema(BaseModel):
    model_config = ConfigDict(extra="allow")

    like_count: int | float | None = None
    retweet_count: int | float | None = None
    reply_count: int | float | None = None
    view_count: int | str | None = None


class BronzePost(BaseModel):
    """Document bronze (collection `posts`)."""

    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {
                "id": "6afed950763f986d3cfdaeb0",
                "source": "twitter",
                "source_post_id": "2123324012017455256",
                "layer": "bronze",
                "query": "#Depression",
                "text": "I have been struggling with depression for years...",
                "text_clean": "I have been struggling with depression for years",
                "lang": "en",
                "created_at": "Thu Nov 19 07:54:28 +0000 2026",
                "scraped_at": "2026-11-19T11:11:12.523000",
                "author": {
                    "id": "123",
                    "username": "example_user",
                    "name": "Example User",
                },
                "metrics": {
                    "like_count": 2,
                    "retweet_count": 0,
                    "reply_count": 1,
                    "view_count": "219",
                },
                "hashtags": ["depression"],
                "urls": [],
                "url": "https://x.com/example_user/status/2123324012017455256",
            }
        },
    )

    id: str
    source: str
    source_post_id: str
    layer: str = "bronze"
    query: str | None = None
    text: str | None = None
    text_clean: str | None = None
    lang: str | None = None
    created_at: str | None = None
    scraped_at: str | None = None
    inserted_at: str | None = None
    author: AuthorSchema | dict[str, Any] | None = None
    metrics: MetricsSchema | dict[str, Any] | None = None
    hashtags: list[Any] = Field(default_factory=list)
    urls: list[Any] = Field(default_factory=list)
    url: str | None = None
    raw: dict[str, Any] | None = None


class BronzePostsResponse(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "total": 494,
                "limit": 20,
                "skip": 0,
                "count": 20,
                "items": [
                    {
                        "id": "6afed950763f986d3cfdaeb0",
                        "source": "twitter",
                        "source_post_id": "2123324012017455256",
                        "layer": "bronze",
                        "query": "#Depression",
                        "text": "I have been struggling with depression for years...",
                        "lang": "en",
                        "author": {"username": "example_user"},
                    }
                ],
            }
        }
    )

    total: int = Field(..., description="Nombre total de posts matching les filtres")
    limit: int
    skip: int
    count: int = Field(..., description="Nombre d'items dans cette page")
    items: list[BronzePost]


class SilverPost(BaseModel):
    """Document silver (collection `cleaned_posts`)."""

    model_config = ConfigDict(
        extra="allow",
        json_schema_extra={
            "example": {
                "id": "abc123",
                "source": "twitter",
                "source_post_id": "2123324012017455256",
                "bronze_id": "6afed950763f986d3cfdaeb0",
                "layer": "silver",
                "original_text": "I feel #Depression today @friend https://t.co/abc 😭",
                "cleaned_text": "i feel depression today",
                "cleaner_version": "1.0.0",
                "lang": "en",
                "query": "#Depression",
            }
        },
    )

    id: str | None = None
    source: str
    source_post_id: str
    bronze_id: str | None = None
    layer: str = "silver"
    query: str | None = None
    lang: str | None = None
    original_text: str | None = None
    cleaned_text: str
    author: AuthorSchema | dict[str, Any] | None = None
    created_at: str | None = None
    cleaned_at: str | None = None
    inserted_at: str | None = None
    url: str | None = None
    cleaner_version: str | None = None


class SilverPostsResponse(BaseModel):
    total: int
    limit: int
    skip: int
    count: int
    items: list[SilverPost]


class CleanTextResponse(BaseModel):
    original_text: str
    cleaned_text: str
    cleaner_version: str
    stats: dict[str, int]


class CleanBatchResponse(BaseModel):
    bronze_read: int
    bronze_total_matching: int
    silver_written: int
    skipped_empty_after_clean: int
    mongo: dict[str, int]
    cleaner_version: str


class SentimentPrediction(BaseModel):
    """Résultat sentiment (mapping 5 → 3 classes)."""

    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "sentiment": "negative",
                "confidence": 0.81,
                "fine_label": "Very Negative",
                "fine_confidence": 0.62,
                "fine_scores": {
                    "Very Negative": 0.62,
                    "Negative": 0.19,
                    "Neutral": 0.1,
                    "Positive": 0.06,
                    "Very Positive": 0.03,
                },
                "sentiment_scores": {
                    "negative": 0.81,
                    "neutral": 0.1,
                    "positive": 0.09,
                },
                "model": "tabularisai/multilingual-sentiment-analysis",
            }
        }
    )

    sentiment: str = Field(..., description="negative | neutral | positive")
    confidence: float
    fine_label: str = Field(..., description="Label brut 5 classes du modèle")
    fine_confidence: float
    fine_scores: dict[str, float]
    sentiment_scores: dict[str, float]
    model: str


class ThemeItem(BaseModel):
    theme: str
    label_raw: str | None = None
    score: float


class ThemePrediction(BaseModel):
    dominant_theme: str | None = None
    themes: list[ThemeItem] = Field(default_factory=list)
    all_theme_scores: list[ThemeItem] = Field(default_factory=list)
    theme_model: str
    theme_threshold: float


class GoldAnalysis(BaseModel):
    """Document gold (collection `posts_analysis`)."""

    model_config = ConfigDict(extra="allow")

    id: str | None = None
    source: str
    source_post_id: str
    silver_id: str | None = None
    bronze_id: str | None = None
    layer: str = "gold"
    query: str | None = None
    lang: str | None = None
    cleaned_text: str | None = None
    author: AuthorSchema | dict[str, Any] | None = None
    url: str | None = None
    sentiment: str
    confidence: float
    sentiment_scores: dict[str, float] | None = None
    fine_label: str | None = None
    fine_confidence: float | None = None
    fine_scores: dict[str, float] | None = None
    sentiment_model: str | None = None
    themes: list[ThemeItem] | list[dict[str, Any]] | None = None
    dominant_theme: str | None = None
    all_theme_scores: list[ThemeItem] | list[dict[str, Any]] | None = None
    theme_model: str | None = None
    theme_threshold: float | None = None
    analyzed_at: str | None = None
    inserted_at: str | None = None


class GoldAnalysesResponse(BaseModel):
    total: int
    limit: int
    skip: int
    count: int
    items: list[GoldAnalysis]


class AnalyzeBatchResponse(BaseModel):
    silver_read: int
    silver_total_matching: int
    gold_written: int
    skipped_empty: int
    mongo: dict[str, int]
    sample: list[dict[str, Any]] = Field(default_factory=list)


class HealthResponse(BaseModel):
    status: str
    mongo: dict[str, Any]


class StubResponse(BaseModel):
    detail: str = Field(..., description="Endpoint prévu, pas encore implémenté")
    next_step: str
