"""Routes silver — nettoyage / normalisation → `cleaned_posts`."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from src.api.schemas import (
    CleanBatchResponse,
    CleanTextResponse,
    SilverPost,
    SilverPostsResponse,
)
from src.cleaner import clean_bronze_batch, clean_bronze_by_id, clean_payload
from src.db.cleaned_posts_repository import get_cleaned_post, list_cleaned_posts

router = APIRouter(prefix="/clean", tags=["silver-clean"])


class CleanTextRequest(BaseModel):
    text: str = Field(..., min_length=1, description="Raw text to clean")
    lowercase: bool = True


class CleanBatchRequest(BaseModel):
    source: str | None = Field(None, description="twitter | facebook")
    lang: str | None = None
    query: str | None = Field(None, description="e.g. #Depression")
    limit: int = Field(50, ge=1, le=500)
    skip: int = Field(0, ge=0)
    lowercase: bool = True


@router.post("/text", response_model=CleanTextResponse)
def clean_single_text(body: CleanTextRequest) -> CleanTextResponse:
    """Clean one text (preview only, no Mongo write)."""
    return CleanTextResponse.model_validate(
        clean_payload(body.text, lowercase=body.lowercase)
    )


@router.post("/batch", response_model=CleanBatchResponse)
def clean_bronze_to_silver(body: CleanBatchRequest) -> CleanBatchResponse:
    """Read bronze `posts`, clean, upsert silver `cleaned_posts`."""
    return CleanBatchResponse.model_validate(
        clean_bronze_batch(
            source=body.source,
            lang=body.lang,
            query=body.query,
            limit=body.limit,
            skip=body.skip,
            lowercase=body.lowercase,
        )
    )


@router.post("/from-bronze/{post_id}", response_model=SilverPost)
def clean_one_bronze_post(post_id: str, lowercase: bool = True) -> SilverPost:
    """Clean one bronze post by id → silver."""
    doc = clean_bronze_by_id(post_id, lowercase=lowercase)
    if doc is None:
        raise HTTPException(
            status_code=404,
            detail="Post bronze introuvable ou texte vide après clean",
        )
    # Re-read from DB to include id / cleaned_at, or return constructed doc
    saved = get_cleaned_post(doc["source_post_id"]) or doc
    return SilverPost.model_validate(saved)


@router.get("/posts", response_model=SilverPostsResponse)
def get_silver_posts(
    source: str | None = Query(None),
    lang: str | None = Query(None),
    query: str | None = Query(None),
    limit: int = Query(20, ge=1, le=200),
    skip: int = Query(0, ge=0),
) -> SilverPostsResponse:
    """List silver posts (`cleaned_posts`)."""
    return SilverPostsResponse.model_validate(
        list_cleaned_posts(
            source=source,
            lang=lang,
            query=query,
            limit=limit,
            skip=skip,
        )
    )


@router.get("/posts/{post_id}", response_model=SilverPost)
def get_silver_post(post_id: str) -> SilverPost:
    """Get one silver post."""
    doc = get_cleaned_post(post_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Post silver introuvable")
    return SilverPost.model_validate(doc)
