"""
Orchestration des pipelines médallion.

- full     : scrape → clean → ML (sentiment + thèmes) → gold
- from_db  : clean (bronze→silver) → ML → gold   (sans scraping)
"""

from __future__ import annotations

import asyncio
from typing import Any

from src.cleaner.pipeline import clean_bronze_batch
from src.config import SCRAPE_HASHTAG, SCRAPE_MAX_POSTS, SCRAPE_MAX_SCAN
from src.ml.analysis_pipeline import analyze_silver_batch
from src.scrapers.twitter_scraper import scrape_and_store


def run_pipeline_without_scraping(
    *,
    source: str = "twitter",
    query: str | None = None,
    clean_limit: int = 50,
    clean_skip: int = 0,
    analyze_limit: int = 50,
    analyze_skip: int = 0,
    with_themes: bool = True,
) -> dict[str, Any]:
    """bronze existant → silver → gold."""
    clean_stats = clean_bronze_batch(
        source=source,
        query=query,
        limit=clean_limit,
        skip=clean_skip,
    )
    analyze_stats = analyze_silver_batch(
        source=source,
        query=query,
        limit=analyze_limit,
        skip=analyze_skip,
        with_themes=with_themes,
    )
    return {
        "pipeline": "without_scraping",
        "steps": {
            "clean": clean_stats,
            "analyze": analyze_stats,
        },
    }


def run_full_pipeline(
    *,
    query: str | None = None,
    scrape_limit: int | None = None,
    max_scan: int | None = None,
    clean_limit: int = 50,
    analyze_limit: int = 50,
    with_themes: bool = True,
    source: str = "twitter",
) -> dict[str, Any]:
    """scrape → clean → ML → gold."""
    query = query or SCRAPE_HASHTAG
    scrape_limit = scrape_limit if scrape_limit is not None else min(SCRAPE_MAX_POSTS, 50)
    max_scan = max_scan if max_scan is not None else SCRAPE_MAX_SCAN

    scrape_stats = asyncio.run(
        scrape_and_store(
            query=query,
            limit=scrape_limit,
            max_scan=max_scan,
            verbose=True,
        )
    )

    # Clean / analyze on the just-scraped query
    rest = run_pipeline_without_scraping(
        source=source,
        query=query,
        clean_limit=clean_limit,
        analyze_limit=analyze_limit,
        with_themes=with_themes,
    )
    return {
        "pipeline": "full",
        "steps": {
            "scrape": scrape_stats,
            "clean": rest["steps"]["clean"],
            "analyze": rest["steps"]["analyze"],
        },
    }
