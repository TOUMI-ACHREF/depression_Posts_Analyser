"""
Scraper Facebook #Depression (Playwright) → Mongo bronze `posts`.

- délais aléatoires anti-blocage
- filtre posts textuels
- session Playwright optionnelle (scripts/fb_storage.json)
"""

from __future__ import annotations

import hashlib
import os
import random
import re
import time
from pathlib import Path
from typing import Any
from urllib.parse import quote

from src.config import (
    FB_STORAGE_FILE,
    SCRAPE_HASHTAG,
    SCRAPE_MAX_POSTS,
    SCRAPE_MIN_CHARS,
    SCRAPE_MIN_WORDS,
)
from src.scrapers.text_filter import extract_plain_text, has_meaningful_text

FB_STORAGE = FB_STORAGE_FILE


def sleep_jitter(min_s: float = 1.2, max_s: float = 3.0, label: str = "") -> None:
    delay = random.uniform(min_s, max_s)
    if label:
        print(f"  … pause {delay:.1f}s ({label})")
    time.sleep(delay)


def _make_source_post_id(post: dict[str, Any]) -> str:
    if post.get("url"):
        return hashlib.sha1(post["url"].encode("utf-8")).hexdigest()[:24]
    base = (post.get("text") or "")[:200]
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:24]


def normalize_facebook_post(post: dict[str, Any], *, query: str) -> dict[str, Any]:
    """Adapte le dict FB au schéma bronze (comme Twitter)."""
    text = post.get("text")
    return {
        "id": _make_source_post_id(post),
        "text": text,
        "text_clean": post.get("text_clean") or extract_plain_text(text),
        "created_at": post.get("created_at"),
        "lang": post.get("lang"),
        "like_count": post.get("like_count"),
        "retweet_count": None,
        "reply_count": post.get("reply_count"),
        "view_count": post.get("view_count"),
        "hashtags": post.get("hashtags") or [query.lstrip("#").lower()],
        "urls": post.get("urls") or [],
        "author": {
            "id": post.get("author_id"),
            "username": post.get("author_username"),
            "name": post.get("author_name"),
        },
        "url": post.get("url"),
    }


async def dismiss_cookies(page) -> None:
    candidates = [
        page.get_by_role(
            "button",
            name=re.compile(
                r"Allow all cookies|Autoriser tous les cookies|Accept all|Tout accepter|"
                r"Allow essential|Autoriser les cookies essentiels",
                re.I,
            ),
        ),
        page.get_by_role("button", name=re.compile(r"^Allow$|^Autoriser$", re.I)),
        page.locator('button[data-cookiebanner="accept_button"]'),
    ]
    for loc in candidates:
        try:
            if await loc.count() > 0 and await loc.first.is_visible():
                await loc.first.click(timeout=2000)
                print("[fb] cookie banner fermée")
                sleep_jitter(0.8, 1.5, "après cookies")
                return
        except Exception:
            continue


async def maybe_wait_for_manual_login(page, timeout_s: int = 90) -> None:
    html = (await page.content()).lower()
    if "login" not in page.url.lower() and "log in" not in html and "se connecter" not in html:
        return
    print(f"[fb] login requis — connecte-toi dans le navigateur (max {timeout_s}s)…")
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        sleep_jitter(2.0, 3.5, "attente login")
        articles = await page.locator('div[role="article"]').count()
        if articles > 0 and "login" not in page.url.lower():
            print("[fb] session OK")
            return


async def expand_see_more(article) -> None:
    try:
        btn = article.get_by_role(
            "button",
            name=re.compile(r"See more|Voir plus|Afficher la suite", re.I),
        )
        if await btn.count() > 0:
            await btn.first.click(timeout=1500)
            sleep_jitter(0.4, 1.0, "see more")
    except Exception:
        pass


async def extract_from_article(article) -> dict[str, Any] | None:
    await expand_see_more(article)
    text = ""
    for sel in [
        '[data-ad-preview="message"]',
        '[data-ad-comet-preview="message"]',
        'div[dir="auto"]',
    ]:
        nodes = article.locator(sel)
        n = await nodes.count()
        chunks: list[str] = []
        for i in range(min(n, 8)):
            try:
                t = (await nodes.nth(i).inner_text(timeout=1000)).strip()
                if t and t not in chunks:
                    chunks.append(t)
            except Exception:
                continue
        if chunks:
            text = max(chunks, key=len)
            if len(text) > 30:
                break

    if not text:
        try:
            text = (await article.inner_text(timeout=2000)).strip()
            text = "\n".join(text.splitlines()[:12]).strip()
        except Exception:
            return None

    permalink = None
    for sel in [
        'a[href*="/posts/"]',
        'a[href*="permalink.php"]',
        'a[href*="/story.php"]',
        'a[href*="/reel/"]',
        'a[href*="pfbid"]',
    ]:
        links = article.locator(sel)
        if await links.count() == 0:
            continue
        try:
            href = await links.first.get_attribute("href")
            if href:
                permalink = href.split("?")[0]
                if permalink.startswith("/"):
                    permalink = "https://www.facebook.com" + permalink
                break
        except Exception:
            continue

    author = None
    try:
        author_loc = article.locator("h3 a, h4 a, strong a").first
        if await author_loc.count() > 0:
            author = (await author_loc.inner_text(timeout=1000)).strip()
    except Exception:
        pass

    return {
        "text": text,
        "text_clean": extract_plain_text(text),
        "author_name": author,
        "url": permalink,
        "source": "facebook",
    }


async def scrape_hashtag(
    query: str | None = None,
    *,
    limit: int | None = None,
    min_chars: int | None = None,
    min_words: int | None = None,
    max_scrolls: int = 12,
    headed: bool = False,
    storage_path: Path | None = None,
    save_storage: bool = False,
    login_wait_s: int = 90,
    verbose: bool = True,
) -> list[dict[str, Any]]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright manquant: pip install playwright && playwright install chromium"
        ) from exc

    query = query or SCRAPE_HASHTAG
    tag = query.lstrip("#")
    limit = limit if limit is not None else min(SCRAPE_MAX_POSTS, 50)
    min_chars = min_chars if min_chars is not None else SCRAPE_MIN_CHARS
    min_words = min_words if min_words is not None else SCRAPE_MIN_WORDS
    storage_path = storage_path or FB_STORAGE

    url = f"https://www.facebook.com/hashtag/{quote(tag)}"
    results: list[dict[str, Any]] = []
    seen: set[str] = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not headed,
            slow_mo=200 if headed else 0,
            args=["--disable-blink-features=AutomationControlled"],
        )
        ctx_kwargs: dict[str, Any] = {
            "locale": "fr-FR",
            "viewport": {"width": 1365, "height": 900},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
        }
        if storage_path.is_file():
            ctx_kwargs["storage_state"] = str(storage_path)
            if verbose:
                print(f"[fb] storage: {storage_path}")

        context = await browser.new_context(**ctx_kwargs)
        page = await context.new_page()

        if verbose:
            print(f"[fb] goto {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        sleep_jitter(2.0, 4.0, "chargement")
        await dismiss_cookies(page)
        sleep_jitter(1.0, 2.5, "stabilisation")

        if headed:
            await maybe_wait_for_manual_login(page, timeout_s=login_wait_s)

        scrolls = 0
        while len(results) < limit and scrolls < max_scrolls:
            articles = page.locator('div[role="article"]')
            count = await articles.count()
            if verbose:
                print(f"[fb] articles={count} kept={len(results)} scroll={scrolls}")

            for i in range(count):
                if len(results) >= limit:
                    break
                try:
                    raw = await extract_from_article(articles.nth(i))
                except Exception as exc:
                    if verbose:
                        print(f"  skip[{i}]: {exc}")
                    continue
                if not raw or not raw.get("text"):
                    continue
                if not has_meaningful_text(
                    raw["text"], min_chars=min_chars, min_words=min_words
                ):
                    continue

                key = (raw.get("text_clean") or "")[:120].lower()
                if key in seen:
                    continue
                seen.add(key)

                post = normalize_facebook_post(raw, query=f"#{tag}")
                results.append(post)
                if verbose:
                    print(f"  keep [{len(results)}/{limit}] {post['author'].get('name')!r}")
                sleep_jitter(1.0, 2.5, "entre posts")

            if len(results) >= limit:
                break
            await page.mouse.wheel(0, random.randint(900, 1600))
            scrolls += 1
            sleep_jitter(2.0, 4.5, "scroll")

        if save_storage:
            await context.storage_state(path=str(storage_path))
            if verbose:
                print(f"[fb] storage sauvé → {storage_path}")

        await browser.close()

    if verbose:
        print(f"[fb] kept={len(results)}")
    return results


async def scrape_and_store(
    query: str | None = None,
    *,
    limit: int | None = None,
    min_chars: int | None = None,
    min_words: int | None = None,
    max_scrolls: int = 12,
    headed: bool = False,
    storage_path: Path | None = None,
    save_storage: bool = False,
    login_wait_s: int = 90,
    verbose: bool = True,
) -> dict[str, Any]:
    """Scrape Facebook + upsert bronze `posts` (source=facebook)."""
    from src.db.posts_repository import count_posts, upsert_posts

    query = query or SCRAPE_HASHTAG
    posts = await scrape_hashtag(
        query,
        limit=limit,
        min_chars=min_chars,
        min_words=min_words,
        max_scrolls=max_scrolls,
        headed=headed,
        storage_path=storage_path,
        save_storage=save_storage,
        login_wait_s=login_wait_s,
        verbose=verbose,
    )
    if not posts:
        return {
            "scraped": 0,
            "upserted": 0,
            "modified": 0,
            "total_facebook_posts": count_posts("facebook"),
            "query": query,
        }

    result = upsert_posts(posts, query=query if query.startswith("#") else f"#{query.lstrip('#')}", source="facebook")
    summary = {
        "scraped": len(posts),
        "upserted": result.upserted_count,
        "modified": result.modified_count,
        "matched": result.matched_count,
        "total_facebook_posts": count_posts("facebook"),
        "query": query,
    }
    if verbose:
        print(f"[mongo] facebook bronze → {summary}")
    return summary
