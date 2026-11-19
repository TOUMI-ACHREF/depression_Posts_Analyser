"""
Test de récupération de posts Facebook liés à #Depression.

Deux modes :
1) Meta Content Library API  -> path "facebook/posts/preview"
   (nécessite Secure Research Environment / cleanroom approuvé ;
    le package metacontentlibraryapi n'est PAS installable en local)
2) Graph API (fallback local) -> pages/search + /{page-id}/feed
   Docs : https://developers.facebook.com/docs/graph-api/overview

Usage Content Library (dans le Jupyter SRE) :
    python scripts/test_facebook_pub_api.py --mode content-library --query "#Depression"

Usage Graph API (local) :
    set FACEBOOK_ACCESS_TOKEN=EAAB...
    python scripts/test_facebook_pub_api.py --mode graph --query Depression --max-pages 3

Sortie JSON dans scripts/output/
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:  # pragma: no cover
    print("Installez requests : pip install requests")
    sys.exit(1)

ROOT_DIR = Path(__file__).resolve().parents[1]
OUTPUT_DIR = Path(__file__).resolve().parent / "output"
GRAPH_VERSION = "v21.0"
GRAPH_BASE = f"https://graph.facebook.com/{GRAPH_VERSION}"


def load_dotenv(path: Path | None = None) -> None:
    """Charge le fichier .env à la racine du projet (sans dépendance externe)."""
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

# Champs utiles pour inspecter ce que l'API peut renvoyer
DEFAULT_POST_FIELDS = ",".join(
    [
        "id",
        "message",
        "created_time",
        "permalink_url",
        "full_picture",
        "shares",
        "reactions.summary(true)",
        "comments.summary(true)",
        "from{id,name}",
        "status_type",
        "type",
    ]
)

DEFAULT_MCL_FIELDS = "id,text,lang,create_time,content_type,views,surface"


# ---------------------------------------------------------------------------
# Meta Content Library — facebook/posts/preview
# ---------------------------------------------------------------------------
def run_content_library(
    query: str,
    fields: str,
    max_pages: int,
    lang: str | None,
    since: str | None,
    until: str | None,
) -> dict[str, Any]:
    """
    Appelle client.get(path='facebook/posts/preview', ...).

    Disponible uniquement dans Meta Secure Research Environment
    (ou cleanroom tiers approuvé). Pas d'export de microdata hors environnement.
    """
    try:
        from metacontentlibraryapi import MetaContentLibraryAPIClient as client
    except ImportError as exc:
        raise RuntimeError(
            "Le package 'metacontentlibraryapi' n'est pas disponible localement.\n"
            "facebook/posts/preview fait partie de Meta Content Library API, "
            "accessible seulement dans Secure Research Environment / cleanroom "
            "(ICPSR, CASD, etc.).\n"
            "Docs : https://developers.facebook.com/docs/content-library-and-api/\n"
            "Relancez avec --mode graph pour tester la Graph API en local."
        ) from exc

    client.set_default_version(client.LATEST_VERSION)

    params: dict[str, Any] = {
        "q": query,
        "fields": fields,
        "sort": "newest_to_oldest",
        "search_scope": "post_text_only",
    }
    if lang:
        params["lang"] = lang
    if since:
        params["since"] = since
    if until:
        params["until"] = until

    print(f"[MCL] GET facebook/posts/preview  params={params}")
    response = client.get(path="facebook/posts/preview", params=params)

    pages: list[Any] = []
    page_num = 1
    while True:
        payload = response.json() if hasattr(response, "json") else json.loads(response.text)
        pages.append(payload)
        data = payload.get("data") or []
        print(f"[MCL] page {page_num}: {len(data)} résultat(s)")
        if data:
            _preview_items(data, source="content-library")

        if page_num >= max_pages or not client.has_next_page(response):
            break
        response = client.query_next_page(response)
        page_num += 1

    all_posts = []
    for page in pages:
        all_posts.extend(page.get("data") or [])

    return {
        "mode": "content-library",
        "path": "facebook/posts/preview",
        "query": query,
        "params": params,
        "pages_fetched": len(pages),
        "total_posts": len(all_posts),
        "posts": all_posts,
        "raw_pages": pages,
        "available_keys_sample": _collect_keys(all_posts),
        "notes": [
            "IDs = Meta Content Library IDs (pas les IDs Facebook publics).",
            "Export / download hors cleanroom interdit par les termes Meta.",
            "Profils : publics + vérifiés ou seuil de followers (ex. 100+ en v6).",
        ],
    }


# ---------------------------------------------------------------------------
# Graph API fallback (test local réaliste pour le mini-projet)
# ---------------------------------------------------------------------------
def _graph_get(path: str, token: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    query = dict(params or {})
    query["access_token"] = token
    url = f"{GRAPH_BASE}/{path.lstrip('/')}"
    resp = requests.get(url, params=query, timeout=30)
    try:
        body = resp.json()
    except ValueError:
        body = {"raw": resp.text}
    if resp.status_code >= 400:
        raise RuntimeError(
            f"Graph API {resp.status_code} on {path}: "
            f"{json.dumps(body, ensure_ascii=False)[:800]}"
        )
    return body


def run_graph_api(
    query: str,
    token: str,
    max_pages: int,
    posts_per_page: int,
    page_limit: int,
) -> dict[str, Any]:
    """
    La Graph API ne permet plus de chercher tous les posts publics par hashtag
    (search type=post déprécié depuis v2.0).

    Stratégie de test :
      1) pages/search?q=<terme>
      2) pour chaque page : /{page-id}/feed (ou /posts)
      3) filtrer les posts contenant le hashtag / mot-clé

    Permissions / features souvent nécessaires :
      - Page Public Content Access (App Review) pour pages non gérées
      - ou Page access token si vous administrez la page
    """
    print(f"[Graph] Recherche de pages pour q={query!r}")
    pages_resp = _graph_get(
        "pages/search",
        token,
        {
            "q": query.lstrip("#"),
            "fields": "id,name,link,fan_count,category,about",
            "limit": page_limit,
        },
    )
    pages = pages_resp.get("data") or []
    print(f"[Graph] {len(pages)} page(s) trouvée(s)")

    keyword = query.lstrip("#").lower()
    collected: list[dict[str, Any]] = []
    page_errors: list[dict[str, Any]] = []

    for page in pages:
        page_id = page.get("id")
        page_name = page.get("name")
        print(f"[Graph] feed page={page_name!r} id={page_id}")
        next_url: str | None = None
        params = {
            "fields": DEFAULT_POST_FIELDS,
            "limit": min(posts_per_page, 100),
        }

        for page_idx in range(max_pages):
            try:
                if next_url:
                    resp = requests.get(next_url, timeout=30)
                    body = resp.json()
                    if resp.status_code >= 400:
                        raise RuntimeError(json.dumps(body, ensure_ascii=False)[:500])
                else:
                    body = _graph_get(f"{page_id}/feed", token, params)
            except Exception as exc:  # noqa: BLE001 — on continue les autres pages
                page_errors.append({"page_id": page_id, "page_name": page_name, "error": str(exc)})
                print(f"  ! erreur: {exc}")
                break

            posts = body.get("data") or []
            print(f"  page feed {page_idx + 1}: {len(posts)} post(s)")
            for post in posts:
                message = (post.get("message") or "").lower()
                if keyword in message or f"#{keyword}" in message:
                    enriched = {
                        **post,
                        "_matched_keyword": query,
                        "_source_page": {"id": page_id, "name": page_name},
                    }
                    collected.append(enriched)

            paging = body.get("paging") or {}
            next_url = paging.get("next")
            if not next_url:
                break

    if collected:
        _preview_items(collected[:5], source="graph")

    return {
        "mode": "graph",
        "graph_version": GRAPH_VERSION,
        "query": query,
        "pages_found": pages,
        "matched_posts": collected,
        "total_matched_posts": len(collected),
        "page_errors": page_errors,
        "available_keys_sample": _collect_keys(collected),
        "notes": [
            "Pas de recherche globale de posts par hashtag sur Graph API moderne.",
            "Page Public Content Access requis pour lire le feed de pages non gérées.",
            "Champs typiques utiles au pipeline: id, message, created_time, permalink_url.",
            "Pour une vraie recherche hashtag large, Meta Content Library "
            "(facebook/posts/preview) est l'API prévue — accès recherche uniquement.",
        ],
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _collect_keys(items: list[dict[str, Any]]) -> list[str]:
    keys: set[str] = set()
    for item in items[:20]:
        if isinstance(item, dict):
            keys.update(item.keys())
    return sorted(keys)


def _preview_items(items: list[dict[str, Any]], source: str, limit: int = 3) -> None:
    print(f"\n--- Aperçu ({source}) ---")
    for i, item in enumerate(items[:limit], start=1):
        text = item.get("text") or item.get("message") or ""
        snippet = (text[:180] + "…") if len(text) > 180 else text
        print(f"[{i}] id={item.get('id')}")
        print(f"    keys={sorted(item.keys())}")
        print(f"    text={snippet!r}")
        if "lang" in item:
            print(f"    lang={item.get('lang')}")
        if "created_time" in item:
            print(f"    created_time={item.get('created_time')}")
        if "create_time" in item:
            print(f"    create_time={item.get('create_time')}")
        if "views" in item:
            print(f"    views={item.get('views')}")
        print()


def save_result(payload: dict[str, Any], mode: str) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = OUTPUT_DIR / f"facebook_{mode}_{stamp}.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Test facebook/posts/preview (MCL) ou Graph API (fallback)."
    )
    parser.add_argument(
        "--mode",
        choices=["content-library", "graph", "auto"],
        default="auto",
        help="auto: Content Library si package présent, sinon Graph API",
    )
    parser.add_argument(
        "--query",
        default="#Depression",
        help="Mot-clé / hashtag à rechercher (défaut: #Depression)",
    )
    parser.add_argument(
        "--fields",
        default=DEFAULT_MCL_FIELDS,
        help="Champs MCL à demander (mode content-library)",
    )
    parser.add_argument("--lang", default=None, help="Filtre langue ISO (ex: fr,en)")
    parser.add_argument("--since", default=None, help="Date début YYYY-MM-DD (MCL)")
    parser.add_argument("--until", default=None, help="Date fin YYYY-MM-DD (MCL)")
    parser.add_argument("--max-pages", type=int, default=2, help="Pages de résultats max")
    parser.add_argument(
        "--page-limit",
        type=int,
        default=5,
        help="Nombre de pages Facebook à explorer (mode graph)",
    )
    parser.add_argument(
        "--posts-per-page",
        type=int,
        default=25,
        help="Posts par requête feed (mode graph, max 100)",
    )
    parser.add_argument(
        "--token",
        default=os.getenv("FACEBOOK_ACCESS_TOKEN") or os.getenv("FB_ACCESS_TOKEN"),
        help="Access token Graph API (ou env FACEBOOK_ACCESS_TOKEN)",
    )
    parser.add_argument(
        "--no-save",
        action="store_true",
        help="Ne pas écrire le JSON dans scripts/output/",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    mode = args.mode

    if mode == "auto":
        try:
            import metacontentlibraryapi  # noqa: F401

            mode = "content-library"
            print("[auto] metacontentlibraryapi détecté -> content-library")
        except ImportError:
            mode = "graph"
            print("[auto] pas de metacontentlibraryapi -> graph")

    try:
        if mode == "content-library":
            result = run_content_library(
                query=args.query,
                fields=args.fields,
                max_pages=args.max_pages,
                lang=args.lang,
                since=args.since,
                until=args.until,
            )
        else:
            if not args.token:
                print(
                    "Token manquant.\n"
                    "Exportez FACEBOOK_ACCESS_TOKEN (User/Page/App token) puis relancez.\n"
                    "Créez un token via Graph API Explorer :\n"
                    "  https://developers.facebook.com/tools/explorer/"
                )
                return 2
            result = run_graph_api(
                query=args.query,
                token=args.token,
                max_pages=args.max_pages,
                posts_per_page=args.posts_per_page,
                page_limit=args.page_limit,
            )
    except RuntimeError as exc:
        print(f"ERREUR: {exc}")
        return 1

    print("\n=== Résumé ===")
    print(f"mode              : {result.get('mode')}")
    print(f"query             : {result.get('query')}")
    if "total_posts" in result:
        print(f"total_posts       : {result['total_posts']}")
    if "total_matched_posts" in result:
        print(f"matched_posts     : {result['total_matched_posts']}")
    print(f"clés disponibles  : {result.get('available_keys_sample')}")
    for note in result.get("notes") or []:
        print(f"- {note}")

    if not args.no_save:
        out = save_result(result, mode=str(result.get("mode")))
        print(f"\nJSON sauvegardé : {out}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
