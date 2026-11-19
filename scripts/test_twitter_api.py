"""
Scrape 2–3 posts publics Twitter/X avec le hashtag #Depression.

Sans API officielle payante.
Librairie : twifork (>=2.4.0) — fork maintenu de twikit pour 2026
  (upstream twikit 2.3.3 est cassé). Import inchangé: from twikit import Client

Auth : cookies navigateur uniquement (login Google OK).
  Password login / guest access : non fiables en 2026.

  1) Ouvre https://x.com et connecte-toi (ex: Google)
  2) F12 → Application → Cookies → https://x.com
  3) Copie auth_token et ct0 dans .env
  4) pip uninstall twikit -y
     pip install "twifork[impersonate]>=2.4.0"
  5) python scripts/test_twitter_api.py --limit 3
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
COOKIES_FILE = Path(__file__).resolve().parent / "twitter_cookies.json"

# Codes langue X = pas de vrai contenu linguistique (média / hashtags seuls)
NON_TEXT_LANGS = {"qme", "qht", "zxx", "und"}
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
MENTION_RE = re.compile(r"@\w+")
HASHTAG_RE = re.compile(r"#\w+")
WHITESPACE_RE = re.compile(r"\s+")


def load_dotenv(path: Path | None = None) -> None:
    env_path = path or (ROOT_DIR / ".env")
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("'").strip('"')
        if key and key not in os.environ:
            os.environ[key] = value


load_dotenv()


COOKIE_HELP = """
Auth cookies requise (login Google OK — pas de mot de passe).

1) Va sur https://x.com (déjà connecté)
2) F12 → Application → Cookies → https://x.com
3) Copie dans le .env :

   TWITTER_AUTH_TOKEN=...
   TWITTER_CT0=...

4) pip uninstall twikit -y
   pip install "twifork[impersonate]>=2.4.0"
5) Relance : python scripts/test_twitter_api.py --limit 3
""".strip()


def create_client() -> Any:
    """Client twifork avec impersonation TLS Chrome (évite certains 403)."""
    try:
        from twikit import Client
    except ImportError as exc:
        raise RuntimeError(
            "Package manquant ou mauvais package.\n"
            "  pip uninstall twikit -y\n"
            '  pip install "twifork[impersonate]>=2.4.0"'
        ) from exc

    # impersonate= nécessite twifork[impersonate] (curl_cffi)
    try:
        return Client("en-US", impersonate="chrome124")
    except TypeError:
        # Ancienne signature sans impersonate
        return Client("en-US")


def extract_plain_text(text: str | None) -> str:
    """Retire URLs, @mentions et #hashtags pour juger s'il reste du texte utile."""
    if not text:
        return ""
    cleaned = URL_RE.sub(" ", text)
    cleaned = MENTION_RE.sub(" ", cleaned)
    cleaned = HASHTAG_RE.sub(" ", cleaned)
    cleaned = WHITESPACE_RE.sub(" ", cleaned).strip()
    return cleaned


def has_meaningful_text(
    text: str | None,
    lang: str | None = None,
    min_chars: int = 40,
    min_words: int = 5,
) -> bool:
    """
    True s'il reste assez de prose après nettoyage des hashtags/URLs/mentions.
    Ignore aussi les posts X marqués qme/qht (média / hashtags seuls).
    """
    plain = extract_plain_text(text)
    if len(plain) < min_chars:
        return False
    if len(plain.split()) < min_words:
        return False
    if (lang or "").lower() in NON_TEXT_LANGS and len(plain) < min_chars * 2:
        return False
    return True


def _tweet_to_dict(tweet: Any) -> dict[str, Any]:
    user = getattr(tweet, "user", None)
    username = getattr(user, "screen_name", None) if user else None
    text = getattr(tweet, "text", None) or getattr(tweet, "full_text", None)
    plain = extract_plain_text(text)
    return {
        "id": str(getattr(tweet, "id", "")),
        "text": text,
        "text_clean": plain,
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


def build_cookies_from_env() -> dict[str, str] | None:
    """Construit les cookies depuis .env (idéal pour login Google)."""
    auth_token = os.getenv("TWITTER_AUTH_TOKEN") or os.getenv("AUTH_TOKEN")
    ct0 = os.getenv("TWITTER_CT0") or os.getenv("CT0")
    if not auth_token or not ct0:
        return None
    return {
        "auth_token": auth_token.strip(),
        "ct0": ct0.strip(),
    }


def persist_cookies(client: Any) -> None:
    try:
        client.save_cookies(str(COOKIES_FILE))
        print(f"[X] Cookies sauvés → {COOKIES_FILE.name}")
    except Exception as exc:  # noqa: BLE001
        print(f"[X] Impossible de sauver les cookies: {exc}")


async def login_client(cookies_path: Path) -> Any:
    client = create_client()

    # 1) Fichier cookies déjà présent
    if cookies_path.is_file():
        try:
            client.load_cookies(str(cookies_path))
            await client.user_id()
            print(f"[X] Session OK via {cookies_path.name} (twifork)")
            return client
        except Exception:
            print(f"[X] {cookies_path.name} invalide/expiré — autre méthode…")

    # 2) Cookies navigateur via .env (auth_token + ct0) — login Google OK
    env_cookies = build_cookies_from_env()
    if env_cookies:
        try:
            client.set_cookies(env_cookies, clear_cookies=True)
            await client.user_id()
            print("[X] Session OK via TWITTER_AUTH_TOKEN + TWITTER_CT0 (.env)")
            persist_cookies(client)
            return client
        except Exception as exc:
            raise RuntimeError(
                "auth_token / ct0 invalides ou expirés.\n"
                "Reconnecte-toi sur https://x.com puis recopie les cookies.\n"
                f"Détail: {exc}"
            ) from exc

    raise RuntimeError(COOKIE_HELP)


async def scrape_hashtag(
    query: str,
    limit: int,
    cookies_path: Path,
    min_chars: int,
    min_words: int,
    max_scan: int,
) -> list[dict[str, Any]]:
    client = await login_client(cookies_path)
    search_q = query if query.startswith("#") else f"#{query}"
    # Évite retweets ; on filtre le "texte réel" en Python
    if "-is:retweet" not in search_q:
        search_q = f"{search_q} -is:retweet"

    print(
        f"[X] Recherche {search_q!r} → {limit} posts textuels "
        f"(scan max {max_scan}, min {min_words} mots / {min_chars} chars)…"
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

            post = _tweet_to_dict(tweet)
            if not has_meaningful_text(
                post.get("text"),
                lang=post.get("lang"),
                min_chars=min_chars,
                min_words=min_words,
            ):
                skipped += 1
                preview_skip = (post.get("text") or "")[:80]
                print(f"  skip (média/hashtags) lang={post.get('lang')}: {preview_skip!r}")
                continue

            results.append(post)
            print(f"  keep [{len(results)}/{limit}] @{((post.get('author') or {}).get('username'))}")

        if len(results) >= limit or scanned >= max_scan:
            break

        # Page suivante si disponible
        try:
            tweets = await tweets.next()
        except Exception:
            break

    print(f"[X] scannés={scanned} gardés={len(results)} ignorés={skipped}")
    return results


def preview(posts: list[dict[str, Any]]) -> None:
    print("\n--- Aperçu ---")
    for i, post in enumerate(posts, start=1):
        text = post.get("text_clean") or post.get("text") or ""
        snippet = (text[:180] + "…") if len(text) > 180 else text
        author = (post.get("author") or {}).get("username")
        print(f"[{i}] @{author}  id={post.get('id')}  lang={post.get('lang')}")
        print(f"    text_clean={snippet!r}")
        print(f"    created_at={post.get('created_at')}  likes={post.get('like_count')}")
        print(f"    url={post.get('url')}")
        print()


def save_result(posts: list[dict[str, Any]], query: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = OUTPUT_DIR / f"twitter_scrape_{stamp}.json"
    payload = {
        "mode": "scrape-twifork",
        "query": query,
        "filter": "text_only (ignore hashtag/media-only posts)",
        "total_posts": len(posts),
        "scraped_at": stamp,
        "posts": posts,
        "available_keys": sorted({k for p in posts for k in p.keys()}),
        "notes": [
            "Scraping via twifork (pas l'API officielle payante).",
            "Posts sans prose réelle (hashtags/média seuls) ignorés.",
            "Champ text_clean = texte sans URLs / @ / #.",
        ],
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scrape posts X textuels (#Depression) — ignore média/hashtags seuls."
    )
    parser.add_argument(
        "--query",
        default=os.getenv("SCRAPE_HASHTAG", "#Depression"),
        help="Hashtag ou requête (défaut: #Depression)",
    )
    parser.add_argument("--limit", type=int, default=3, help="Posts textuels à garder (défaut: 3)")
    parser.add_argument(
        "--min-chars",
        type=int,
        default=40,
        help="Min. caractères de texte réel après nettoyage (défaut: 40)",
    )
    parser.add_argument(
        "--min-words",
        type=int,
        default=5,
        help="Min. mots de texte réel après nettoyage (défaut: 5)",
    )
    parser.add_argument(
        "--max-scan",
        type=int,
        default=40,
        help="Max. posts à scanner avant d'abandonner (défaut: 40)",
    )
    parser.add_argument(
        "--cookies",
        default=str(COOKIES_FILE),
        help="Chemin vers twitter_cookies.json",
    )
    parser.add_argument("--no-save", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    limit = max(1, min(args.limit, 10))
    cookies_path = Path(args.cookies)

    try:
        posts = asyncio.run(
            scrape_hashtag(
                query=args.query,
                limit=limit,
                cookies_path=cookies_path,
                min_chars=args.min_chars,
                min_words=args.min_words,
                max_scan=args.max_scan,
            )
        )
    except RuntimeError as exc:
        print(f"ERREUR:\n{exc}")
        return 1
    except Exception as exc:  # noqa: BLE001
        print(f"ERREUR scrape: {type(exc).__name__}: {exc}")
        return 1

    if not posts:
        print(
            "Aucun post textuel trouvé.\n"
            "Augmente --max-scan ou baisse --min-chars / --min-words."
        )
        return 1

    preview(posts)
    print(f"=== {len(posts)} post(s) textuel(s) récupéré(s) ===")

    if not args.no_save:
        out = save_result(posts, args.query)
        print(f"JSON sauvegardé : {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
