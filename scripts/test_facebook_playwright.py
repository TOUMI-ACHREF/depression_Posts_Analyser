"""
Test scrape Facebook #Depression avec Playwright (2 posts seulement).

But :
  - comprendre la structure DOM / sélecteurs
  - petits délais aléatoires pour limiter les blocages
  - pas d'écriture Mongo (test uniquement)

Usage :
  pip install playwright
  playwright install chromium

  python scripts/test_facebook_playwright.py
  python scripts/test_facebook_playwright.py --headed --limit 2

Si Facebook demande une connexion :
  1) lance avec --headed
  2) connecte-toi manuellement dans la fenêtre
  3) le script attend puis continue
  OU fournis un storage state :
     --storage scripts/fb_storage.json
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
DEFAULT_STORAGE = Path(__file__).resolve().parent / "fb_storage.json"

URL_RE = re.compile(r"https?://\S+", re.I)
HASHTAG_RE = re.compile(r"#\w+")
MENTION_RE = re.compile(r"@\w+")
WS_RE = re.compile(r"\s+")


def load_dotenv() -> None:
    env_path = ROOT_DIR / ".env"
    if not env_path.is_file():
        return
    import os

    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, v = line.partition("=")
        k, v = k.strip(), v.strip().strip("'").strip('"')
        if k and k not in os.environ:
            os.environ[k] = v


def sleep_jitter(min_s: float = 1.2, max_s: float = 3.0, label: str = "") -> None:
    delay = random.uniform(min_s, max_s)
    if label:
        print(f"  … pause {delay:.1f}s ({label})")
    time.sleep(delay)


def plain_text(text: str | None) -> str:
    if not text:
        return ""
    t = URL_RE.sub(" ", text)
    t = MENTION_RE.sub(" ", t)
    t = HASHTAG_RE.sub(" ", t)
    return WS_RE.sub(" ", t).strip()


def has_meaningful_text(text: str | None, min_chars: int = 40, min_words: int = 5) -> bool:
    p = plain_text(text)
    return len(p) >= min_chars and len(p.split()) >= min_words


async def dismiss_cookies(page) -> None:
    """Ferme les bannières cookies courantes (FR/EN)."""
    candidates = [
        page.get_by_role("button", name=re.compile(r"Allow all cookies|Autoriser tous les cookies|Accept all|Tout accepter|Allow essential|Autoriser les cookies essentiels", re.I)),
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


async def maybe_wait_for_manual_login(page, timeout_s: int = 120) -> None:
    """Si login wall, laisse l'utilisateur se connecter (mode headed)."""
    content = (await page.content()).lower()
    login_signals = [
        "log in",
        "se connecter",
        "create new account",
        "créer un compte",
        "email address or phone number",
    ]
    if not any(s in content for s in login_signals):
        # aussi via URL
        if "login" not in page.url.lower():
            return

    print(
        f"[fb] Connexion probablement requise.\n"
        f"     Connecte-toi manuellement dans le navigateur (max {timeout_s}s)…"
    )
    deadline = time.time() + timeout_s
    while time.time() < deadline:
        sleep_jitter(2.0, 3.5, "attente login")
        url = page.url.lower()
        html = (await page.content()).lower()
        if "login" not in url and "log in" not in html[:2000]:
            # heuristique soft
            articles = await page.locator('div[role="article"]').count()
            if articles > 0:
                print("[fb] session OK — posts visibles")
                return
    print("[fb] timeout login — on continue quand même")


async def expand_see_more(article) -> None:
    try:
        btn = article.get_by_role(
            "button",
            name=re.compile(r"See more|Voir plus|Afficher la suite", re.I),
        )
        if await btn.count() > 0:
            await btn.first.click(timeout=1500)
            sleep_jitter(0.5, 1.2, "see more")
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
            # prendre le plus long bloc comme corps
            text = max(chunks, key=len)
            if len(text) > 30:
                break

    if not text:
        try:
            text = (await article.inner_text(timeout=2000)).strip()
            # tronquer un peu le bruit UI
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
        "text_clean": plain_text(text),
        "author_name": author,
        "url": permalink,
        "source": "facebook",
        "query": "#Depression",
    }


async def scrape_hashtag(
    *,
    hashtag: str,
    limit: int,
    headed: bool,
    storage: Path | None,
    save_storage: Path | None,
    login_wait_s: int,
) -> list[dict[str, Any]]:
    try:
        from playwright.async_api import async_playwright
    except ImportError as exc:
        raise RuntimeError(
            "Playwright manquant.\n"
            "  pip install playwright\n"
            "  playwright install chromium"
        ) from exc

    tag = hashtag.lstrip("#")
    url = f"https://www.facebook.com/hashtag/{quote(tag)}"

    results: list[dict[str, Any]] = []
    seen_texts: set[str] = set()

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=not headed,
            slow_mo=250 if headed else 0,
            args=["--disable-blink-features=AutomationControlled"],
        )
        context_kwargs: dict[str, Any] = {
            "locale": "fr-FR",
            "viewport": {"width": 1365, "height": 900},
            "user_agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/121.0.0.0 Safari/537.36"
            ),
        }
        if storage and storage.is_file():
            context_kwargs["storage_state"] = str(storage)
            print(f"[fb] storage state: {storage}")

        context = await browser.new_context(**context_kwargs)
        page = await context.new_page()

        print(f"[fb] goto {url}")
        await page.goto(url, wait_until="domcontentloaded", timeout=60000)
        sleep_jitter(2.0, 4.0, "après chargement")

        await dismiss_cookies(page)
        sleep_jitter(1.0, 2.5, "stabilisation")

        await maybe_wait_for_manual_login(page, timeout_s=login_wait_s)

        # Parfois le hashtag redirige / login wall → retry hashtag
        if "hashtag" not in page.url.lower():
            print(f"[fb] URL actuelle={page.url} — nouvel essai hashtag")
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            sleep_jitter(2.0, 3.5, "reload hashtag")

        scrolls = 0
        max_scrolls = 8
        while len(results) < limit and scrolls < max_scrolls:
            articles = page.locator('div[role="article"]')
            count = await articles.count()
            print(f"[fb] articles visibles={count}  gardés={len(results)}  scroll={scrolls}")

            for i in range(count):
                if len(results) >= limit:
                    break
                article = articles.nth(i)
                try:
                    post = await extract_from_article(article)
                except Exception as exc:
                    print(f"  skip article[{i}]: {exc}")
                    continue

                if not post or not post.get("text"):
                    continue
                if not has_meaningful_text(post["text"]):
                    preview = (post["text"] or "")[:70].replace("\n", " ")
                    print(f"  skip (peu de texte): {preview!r}")
                    continue

                key = post["text_clean"][:120].lower()
                if key in seen_texts:
                    continue
                seen_texts.add(key)

                post["scraped_at"] = datetime.now(timezone.utc).isoformat()
                results.append(post)
                print(f"  keep [{len(results)}/{limit}] author={post.get('author_name')!r}")
                sleep_jitter(1.0, 2.2, "entre posts")

            if len(results) >= limit:
                break

            await page.mouse.wheel(0, random.randint(900, 1600))
            scrolls += 1
            sleep_jitter(2.0, 4.5, "scroll")

        if save_storage:
            await context.storage_state(path=str(save_storage))
            print(f"[fb] storage sauvé → {save_storage}")

        await browser.close()

    return results


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="Test Playwright Facebook #Depression (2 posts)")
    p.add_argument("--hashtag", default="Depression")
    p.add_argument("--limit", type=int, default=2)
    p.add_argument("--headed", action="store_true", help="Afficher le navigateur")
    p.add_argument("--storage", default=str(DEFAULT_STORAGE), help="Fichier session Playwright")
    p.add_argument("--save-storage", action="store_true", help="Sauver la session après run")
    p.add_argument("--login-wait", type=int, default=90, help="Secondes pour login manuel")
    p.add_argument("--no-save", action="store_true")
    return p


def main() -> int:
    load_dotenv()
    args = build_parser().parse_args()
    storage = Path(args.storage)
    save_path = storage if args.save_storage else None

    import asyncio

    try:
        posts = asyncio.run(
            scrape_hashtag(
                hashtag=args.hashtag,
                limit=max(1, min(args.limit, 5)),
                headed=args.headed,
                storage=storage if storage.is_file() else None,
                save_storage=save_path,
                login_wait_s=args.login_wait,
            )
        )
    except RuntimeError as exc:
        print(f"ERREUR: {exc}")
        return 1
    except Exception as exc:
        print(f"ERREUR scrape: {type(exc).__name__}: {exc}")
        return 1

    print(f"\n=== {len(posts)} post(s) ===")
    for i, post in enumerate(posts, 1):
        print(f"[{i}] {post.get('author_name')}")
        print(f"    {(post.get('text_clean') or '')[:160]!r}")
        print(f"    url={post.get('url')}")

    if not posts:
        print(
            "Aucun post textuel.\n"
            "Astuce: relance avec --headed --save-storage, connecte-toi, puis réutilise --storage."
        )
        return 1

    if not args.no_save:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        out = OUTPUT_DIR / f"facebook_playwright_{stamp}.json"
        payload = {
            "mode": "playwright-test",
            "query": f"#{args.hashtag.lstrip('#')}",
            "total_posts": len(posts),
            "posts": posts,
            "notes": [
                "Test limité à quelques posts.",
                "Délais aléatoires entre actions.",
                "Facebook peut exiger une session connectée.",
            ],
        }
        out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\nJSON: {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
