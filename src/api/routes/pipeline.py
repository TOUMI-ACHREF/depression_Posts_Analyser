"""Routes d'orchestration : full pipeline / sans scraping."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from src.pipeline import run_full_pipeline, run_pipeline_without_scraping

router = APIRouter(prefix="/pipeline", tags=["pipeline"])


class FullPipelineRequest(BaseModel):
    query: str | None = Field(None, description="Hashtag, défaut SCRAPE_HASHTAG")
    scrape_limit: int = Field(20, ge=1, le=200)
    max_scan: int = Field(100, ge=10, le=2000)
    clean_limit: int = Field(50, ge=1, le=500)
    analyze_limit: int = Field(50, ge=1, le=200)
    with_themes: bool = True
    source: str = "twitter"


class FromBronzePipelineRequest(BaseModel):
    source: str = "twitter"
    query: str | None = None
    clean_limit: int = Field(50, ge=1, le=500)
    clean_skip: int = Field(0, ge=0)
    analyze_limit: int = Field(50, ge=1, le=200)
    analyze_skip: int = Field(0, ge=0)
    with_themes: bool = True


@router.post("/full")
def pipeline_full(body: FullPipelineRequest) -> dict:
    """
    Pipeline complet :
    scrape Twitter → bronze → clean → silver → sentiment+thèmes → gold
    """
    try:
        return run_full_pipeline(
            query=body.query,
            scrape_limit=body.scrape_limit,
            max_scan=body.max_scan,
            clean_limit=body.clean_limit,
            analyze_limit=body.analyze_limit,
            with_themes=body.with_themes,
            source=body.source,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Full pipeline error: {exc}") from exc


@router.post("/from-bronze")
def pipeline_without_scraping(body: FromBronzePipelineRequest) -> dict:
    """
    Pipeline sans scraping :
    bronze existant → clean → silver → sentiment+thèmes → gold
    """
    try:
        return run_pipeline_without_scraping(
            source=body.source,
            query=body.query,
            clean_limit=body.clean_limit,
            clean_skip=body.clean_skip,
            analyze_limit=body.analyze_limit,
            analyze_skip=body.analyze_skip,
            with_themes=body.with_themes,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500, detail=f"From-bronze pipeline error: {exc}"
        ) from exc
