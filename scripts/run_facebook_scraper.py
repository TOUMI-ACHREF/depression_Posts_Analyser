"""
Scrape Facebook #Depression → MongoDB bronze (`posts`, source=facebook).

Local (Mongo Docker sur localhost:27017) :
  docker compose up -d mongo
  python scripts/run_facebook_scraper.py --limit 10 --headed --save-storage

Docker (écrit dans Mongo du compose) :
  voir docker-compose service `facebook-scraper`
"""

from __future__ import annotations

import argparse
import asyncio
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import (  # noqa: E402
    SCRAPE_HASHTAG,
    SCRAPE_MAX_POSTS,
    SCRAPE_MIN_CHARS,
    SCRAPE_MIN_WORDS,
    load_dotenv,
)
from src.db.mongo import ensure_indexes, ping  # noqa: E402
from src.scrapers.facebook_scraper import FB_STORAGE, scrape_and_store  # noqa: E402

load_dotenv()


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Scrape Facebook → MongoDB posts (bronze)")
    p.add_argument("--query", default=os.getenv("SCRAPE_HASHTAG", SCRAPE_HASHTAG))
    p.add_argument("--limit", type=int, default=min(int(os.getenv("SCRAPE_MAX_POSTS", SCRAPE_MAX_POSTS)), 20))
    p.add_argument("--min-chars", type=int, default=SCRAPE_MIN_CHARS)
    p.add_argument("--min-words", type=int, default=SCRAPE_MIN_WORDS)
    p.add_argument(
        "--max-scrolls",
        type=int,
        default=0,
        help="0 = auto (environ limit/2, min 20)",
    )
    p.add_argument("--headed", action="store_true", help="Navigateur visible (login manuel)")
    p.add_argument("--storage", default=str(FB_STORAGE))
    p.add_argument("--save-storage", action="store_true")
    p.add_argument("--login-wait", type=int, default=90)
    return p


def main() -> int:
    args = build_parser().parse_args()

    try:
        status = ping()
        print(f"[mongo] ping ok={status['ok']} uri={status['uri']} db={status['db']}")
    except Exception as exc:
        print(
            "ERREUR MongoDB inaccessible.\n"
            "Lance: docker compose up -d mongo\n"
            "Et utilise MONGO_URI=mongodb://mongo:27017 dans Docker "
            "(ou localhost:27017 si seul le conteneur écoute).\n"
            f"Détail: {exc}"
        )
        return 1

    ensure_indexes()
    storage = Path(args.storage)

    limit = max(1, args.limit)
    max_scrolls = args.max_scrolls if args.max_scrolls > 0 else max(20, limit // 2)

    try:
        summary = asyncio.run(
            scrape_and_store(
                query=args.query,
                limit=limit,
                min_chars=args.min_chars,
                min_words=args.min_words,
                max_scrolls=max_scrolls,
                headed=args.headed,
                storage_path=storage,
                save_storage=args.save_storage,
                login_wait_s=args.login_wait,
            )
        )
    except Exception as exc:
        print(f"ERREUR scrape: {type(exc).__name__}: {exc}")
        return 1

    if summary.get("scraped", 0) == 0:
        print(
            "Aucun post Facebook textuel.\n"
            "Essaie: --headed --save-storage puis reconnecte-toi une fois."
        )
        return 1

    print(
        f"OK — scraped={summary['scraped']} upserted={summary['upserted']} "
        f"modified={summary['modified']} total_facebook_in_db={summary['total_facebook_posts']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
