"""
Scraper Twitter/X (bronze → collection `posts`).

Technique :
  - twifork (fork twikit 2026)
  - auth cookies navigateur (TWITTER_AUTH_TOKEN + TWITTER_CT0)
  - filtre posts textuels (ignore média / hashtags seuls)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from src.config import (
    COOKIES_FILE,
    SCRAPE_HASHTAG,
    SCRAPE_MAX_POSTS,
    SCRAPE_MAX_SCAN,
    SCRAPE_MIN_CHARS,
    SCRAPE_MIN_WORDS,
)
from src.scrapers.text_filter import extract_plain_text, has_meaningful_text

COOKIE_HELP = (
    "Cookies X manquants/expirés.\n"
    "Remplis TWITTER_AUTH_TOKEN et TWITTER_CT0 dans .env "
    "(F12 → Cookies → https://x.com)."
)


def create_client() -> Any:
    try:
        from twikit import Client
    except ImportError as exc:
        raise RuntimeError(
            'Installe twifork : pip install "twifork[impersonate]>=2.4.0"'
        ) from exc

    try:
        return Client("en-US", impersonate="chrome124")
    except TypeError:
        return Client("en-US")


def _cookies_from_env() -> dict[str, str] | None:
    auth_token = os.getenv("TWITTER_AUTH_TOKEN") or os.getenv("AUTH_TOKEN")
    ct0 = os.getenv("TWITTER_CT0") or os.getenv("CT0")
    if not auth_token or not ct0:
        return None
    return {"auth_token": auth_token.strip(), "ct0": ct0.strip()}


def _persist_cookies(client: Any, path: Path) -> None:
    try:
        client.save_cookies(str(path))
    except Exception:
        pass


async def login_client(cookies_path: Path | None = None) -> Any:
    path = cookies_path or COOKIES_FILE
    client = create_client()

    if path.is_file():
        try:
            client.load_cookies(str(path))
            await client.user_id()
            return client
        except Exception:
            pass

    env_cookies = _cookies_from_env()
    if env_cookies:
        try:
            client.set_cookies(env_cookies, clear_cookies=True)
            await client.user_id()
            _persist_cookies(client, path)
            return client
        except Exception as exc:
            raise RuntimeError(f"{COOKIE_HELP}\nDétail: {exc}") from exc

    raise RuntimeError(COOKIE_HELP)


def tweet_to_dict(tweet: Any) -> dict[str, Any]:
    user = getattr(tweet, "user", None)
    username = getattr(user, "screen_name", None) if user else None
    text = getattr(tweet, "text", None) or getattr(tweet, "full_text", None)
    return {
        "id": str(getattr(tweet, "id", "")),
        "text": text,
        "text_clean": extract_plain_text(text),
        "created_at": getattr(tweet, "created_at", None),
        "lang": getattr(tweet, "lang", None),
        "like_count": getattr(tweet, "favorite_count", None)
        or getattr(tweet, "like_count", None),
        "retweet_count": getattr(tweet, "retweet_count", None),
        "reply_count": getattr(tweet, "reply_count", None),
        "view_count": getattr(tweet, "view_count", None),
        "hashtags": list(getattr(tweet, "hashtags", None) or []),
        "urls": list(getattr(tweet, "urls", None) or []),
        "author": {
            "id": str(getattr(user, "id", "")) if user else None,
            "username": username,
            "name": getattr(user, "name", None) if user else None,
        },
        "url": (
            f"https://x.com/{username}/status/{getattr(tweet, 'id', '')}"
            if username and getattr(tweet, "id", None)
            else None
        ),
    }


async def scrape_hashtag(
    query: str | None = None,
    *,
    limit: int | None = None,
    min_chars: int | None = None,
    min_words: int | None = None,
    max_scan: int | None = None,
    cookies_path: Path | None = None,
    verbose: bool = True,
) -> list[dict[str, Any]]:
    """Récupère des posts textuels pour un hashtag (ex: #Depression)."""
    query = query or SCRAPE_HASHTAG
    limit = limit if limit is not None else SCRAPE_MAX_POSTS
    min_chars = min_chars if min_chars is not None else SCRAPE_MIN_CHARS
    min_words = min_words if min_words is not None else SCRAPE_MIN_WORDS
    max_scan = max_scan if max_scan is not None else SCRAPE_MAX_SCAN

    client = await login_client(cookies_path)
    search_q = query if query.startswith("#") else f"#{query}"
    if "-is:retweet" not in search_q:
        search_q = f"{search_q} -is:retweet"

    if verbose:
        print(
            f"[twitter] search={search_q!r} limit={limit} "
            f"max_scan={max_scan} min_words={min_words}"
        )

    results: list[dict[str, Any]] = []
    skipped = 0
    scanned = 0
    tweets = await client.search_tweet(search_q, "Latest")

    while tweets is not None and scanned < max_scan and len(results) < limit:
        batch = list(tweets)
        if not batch:
            break

        for tweet in batch:
            scanned += 1
            if scanned > max_scan or len(results) >= limit:
                break

            post = tweet_to_dict(tweet)
            if not has_meaningful_text(
                post.get("text"),
                lang=post.get("lang"),
                min_chars=min_chars,
                min_words=min_words,
            ):
                skipped += 1
                continue

            results.append(post)
            if verbose:
                author = (post.get("author") or {}).get("username")
                print(f"  keep [{len(results)}/{limit}] @{author}")

        if len(results) >= limit or scanned >= max_scan:
            break

        try:
            tweets = await tweets.next()
        except Exception:
            break

    if verbose:
        print(f"[twitter] scanned={scanned} kept={len(results)} skipped={skipped}")

    return results


async def scrape_and_store(
    query: str | None = None,
    *,
    limit: int | None = None,
    min_chars: int | None = None,
    min_words: int | None = None,
    max_scan: int | None = None,
    cookies_path: Path | None = None,
    verbose: bool = True,
) -> dict[str, Any]:
    """Scrape + upsert dans MongoDB collection bronze `posts`."""
    from src.db.posts_repository import count_posts, upsert_posts

    query = query or SCRAPE_HASHTAG
    posts = await scrape_hashtag(
        query,
        limit=limit,
        min_chars=min_chars,
        min_words=min_words,
        max_scan=max_scan,
        cookies_path=cookies_path,
        verbose=verbose,
    )
    if not posts:
        return {"scraped": 0, "upserted": 0, "modified": 0, "total_twitter_posts": count_posts("twitter")}

    result = upsert_posts(posts, query=query, source="twitter")
    summary = {
        "scraped": len(posts),
        "upserted": result.upserted_count,
        "modified": result.modified_count,
        "matched": result.matched_count,
        "total_twitter_posts": count_posts("twitter"),
        "query": query,
    }
    if verbose:
        print(f"[mongo] posts bronze → {summary}")
    return summary
