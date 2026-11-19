"""Routes bronze — lecture des posts scrapés."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from src.api.schemas import BronzePost, BronzePostsResponse
from src.db.posts_repository import get_bronze_post, list_bronze_posts

router = APIRouter(prefix="/posts", tags=["bronze-posts"])


@router.get(
    "",
    response_model=BronzePostsResponse,
    summary="List bronze posts",
    response_description="Paginated bronze posts from MongoDB collection `posts`",
)
def get_bronze_posts(
    source: str | None = Query(None, description="twitter | facebook"),
    lang: str | None = Query(None, description="Language filter, e.g. en, fr"),
    query: str | None = Query(None, description="Scrape query, e.g. #Depression"),
    limit: int = Query(20, ge=1, le=200, description="Page size"),
    skip: int = Query(0, ge=0, description="Offset"),
    include_raw: bool = Query(False, description="Include raw scrape payload"),
) -> BronzePostsResponse:
    """Return scraped bronze posts (`posts` collection)."""
    data = list_bronze_posts(
        source=source,
        lang=lang,
        query=query,
        limit=limit,
        skip=skip,
        include_raw=include_raw,
    )
    return BronzePostsResponse.model_validate(data)


@router.get(
    "/{post_id}",
    response_model=BronzePost,
    summary="Get one bronze post",
    responses={404: {"description": "Bronze post not found"}},
)
def get_bronze_post_by_id(
    post_id: str,
    include_raw: bool = Query(False),
) -> BronzePost:
    """Get a bronze post by Mongo `id` or `source_post_id`."""
    doc = get_bronze_post(post_id, include_raw=include_raw)
    if not doc:
        raise HTTPException(status_code=404, detail="Post bronze introuvable")
    return BronzePost.model_validate(doc)
