"""
Lance le scraper Twitter et stocke les posts dans MongoDB (bronze: posts).

Usage :
  # démarre Mongo si besoin
  docker compose up -d mongo

  python scripts/run_twitter_scraper.py --limit 10
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import (  # noqa: E402
    SCRAPE_HASHTAG,
    SCRAPE_MAX_POSTS,
    SCRAPE_MAX_SCAN,
    SCRAPE_MIN_CHARS,
    SCRAPE_MIN_WORDS,
    load_dotenv,
)
from src.db.mongo import ensure_indexes, ping  # noqa: E402
from src.scrapers.twitter_scraper import scrape_and_store  # noqa: E402

load_dotenv()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Scrape Twitter → MongoDB posts (bronze)")
    parser.add_argument("--query", default=SCRAPE_HASHTAG)
    parser.add_argument("--limit", type=int, default=min(SCRAPE_MAX_POSTS, 20))
    parser.add_argument("--min-chars", type=int, default=SCRAPE_MIN_CHARS)
    parser.add_argument("--min-words", type=int, default=SCRAPE_MIN_WORDS)
    parser.add_argument("--max-scan", type=int, default=SCRAPE_MAX_SCAN)
    parser.add_argument(
        "--init-db-only",
        action="store_true",
        help="Crée uniquement les index Mongo (pas de scrape)",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    try:
        status = ping()
        print(f"[mongo] ping ok={status['ok']} db={status['db']}")
    except Exception as exc:
        print(
            "ERREUR MongoDB inaccessible.\n"
            "Lance : docker compose up -d mongo\n"
            f"Détail: {exc}"
        )
        return 1

    indexes = ensure_indexes()
    print(
        "[mongo] collections prévues → "
        f"bronze={indexes['collections']['bronze']}, "
        f"silver={indexes['collections']['silver']}, "
        f"gold={indexes['collections']['gold']}"
    )

    if args.init_db_only:
        print("[mongo] indexes posts (bronze) OK")
        return 0

    try:
        summary = asyncio.run(
            scrape_and_store(
                query=args.query,
                limit=max(1, args.limit),
                min_chars=args.min_chars,
                min_words=args.min_words,
                max_scan=args.max_scan,
            )
        )
    except Exception as exc:
        print(f"ERREUR scrape: {type(exc).__name__}: {exc}")
        return 1

    if summary.get("scraped", 0) == 0:
        print("Aucun post textuel trouvé.")
        return 1

    print(
        f"OK — scraped={summary['scraped']} "
        f"upserted={summary['upserted']} "
        f"modified={summary['modified']} "
        f"total_twitter_in_db={summary['total_twitter_posts']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
