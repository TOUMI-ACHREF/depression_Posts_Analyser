"""Routes gold — sentiment + thèmes HF sur silver → `posts_analysis`."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.schemas import (
    AnalyzeBatchResponse,
    GoldAnalysis,
    GoldAnalysesResponse,
    SentimentPrediction,
    ThemePrediction,
)
from src.db.analysis_repository import get_analysis, list_analyses
from src.ml.analysis_pipeline import (
    analyze_silver_batch,
    analyze_silver_by_id,
    analyze_text,
)
from src.ml.theme_detector import predict_themes

router = APIRouter(prefix="/analysis", tags=["analysis-gold"])


class SentimentTextRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Texte à classer (idéalement cleaned)")
    with_themes: bool = False


class ThemeTextRequest(BaseModel):
    text: str = Field(..., min_length=1)
    top_k: int = Field(3, ge=1, le=8)
    threshold: float = Field(0.35, ge=0.0, le=1.0)


class AnalyzeBatchRequest(BaseModel):
    source: str | None = Field(None, description="twitter | facebook")
    lang: str | None = None
    query: str | None = Field(None, description="e.g. #Depression")
    limit: int = Field(20, ge=1, le=100, description="Posts silver à analyser")
    skip: int = Field(0, ge=0)
    with_themes: bool = True


@router.post("/sentiment", response_model=SentimentPrediction)
def predict_text_sentiment(body: SentimentTextRequest) -> SentimentPrediction:
    """Preview sentiment (5→3 classes). Pas d'écriture Mongo."""
    try:
        result = analyze_text(body.text, with_themes=False)["sentiment"]
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Sentiment model error: {exc}") from exc
    return SentimentPrediction.model_validate(result)


@router.post("/themes", response_model=ThemePrediction)
def predict_text_themes(body: ThemeTextRequest) -> ThemePrediction:
    """Preview thèmes zero-shot (mDeBERTa). Pas d'écriture Mongo."""
    try:
        result = predict_themes(
            body.text,
            top_k=body.top_k,
            threshold=body.threshold,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Theme model error: {exc}") from exc
    return ThemePrediction.model_validate(result)


@router.post("/sentiment/batch", response_model=AnalyzeBatchResponse)
def analyze_silver_to_gold(body: AnalyzeBatchRequest) -> AnalyzeBatchResponse:
    """
    Lit `cleaned_posts` (silver), prédit sentiment (+ thèmes), upsert `posts_analysis` (gold).
    """
    try:
        result = analyze_silver_batch(
            source=body.source,
            lang=body.lang,
            query=body.query,
            limit=body.limit,
            skip=body.skip,
            with_themes=body.with_themes,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Batch analysis error: {exc}") from exc
    return AnalyzeBatchResponse.model_validate(result)


@router.post("/sentiment/from-silver/{post_id}", response_model=GoldAnalysis)
def analyze_one_silver_post(
    post_id: str,
    with_themes: bool = True,
) -> GoldAnalysis:
    """Analyse un post silver par id → gold (sentiment + thèmes)."""
    try:
        doc = analyze_silver_by_id(post_id, with_themes=with_themes)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Analysis error: {exc}") from exc
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail="Post silver introuvable ou cleaned_text vide",
        )
    return GoldAnalysis.model_validate(doc)


@router.get("/posts", response_model=GoldAnalysesResponse)
def get_gold_analyses(
    source: str | None = Query(None),
    sentiment: str | None = Query(None, description="negative | neutral | positive"),
    query: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    skip: int = Query(0, ge=0),
) -> GoldAnalysesResponse:
    """Liste les documents gold (`posts_analysis`)."""
    return GoldAnalysesResponse.model_validate(
        list_analyses(
            source=source,
            sentiment=sentiment,
            query=query,
            limit=limit,
            skip=skip,
        )
    )


@router.get("/posts/{post_id}", response_model=GoldAnalysis)
def get_gold_analysis(post_id: str) -> GoldAnalysis:
    """Détail d'une analyse gold."""
    doc = get_analysis(post_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Analyse gold introuvable")
    return GoldAnalysis.model_validate(doc)
