"""Configuration centrale (env + noms des collections médallion)."""

from __future__ import annotations

import os
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
COOKIES_FILE = ROOT_DIR / "scripts" / "twitter_cookies.json"
FB_STORAGE_FILE = ROOT_DIR / "scripts" / "fb_storage.json"


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


def _running_in_docker() -> bool:
    return Path("/.dockerenv").exists() or os.getenv("RUNNING_IN_DOCKER") == "1"


def _resolve_mongo_uri() -> str:
    """
    Source de vérité = Mongo Docker.
    - Dans un conteneur : toujours mongodb://mongo:27017 (sauf override explicite non-localhost)
    - Sur l'hôte : localhost:27017 = port publié du conteneur (Mongo Windows doit rester Stopped)
    """
    uri = os.getenv("MONGO_URI", "mongodb://localhost:27017").strip()
    if _running_in_docker():
        if "localhost" in uri or "127.0.0.1" in uri:
            return "mongodb://mongo:27017"
        return uri or "mongodb://mongo:27017"
    return uri


# --- MongoDB / médallion (Docker only) ---
MONGO_URI = _resolve_mongo_uri()
MONGO_DB = os.getenv("MONGO_DB", "depression_posts")


# bronze → silver → gold
COLLECTION_POSTS = os.getenv("MONGO_COLLECTION_POSTS", "posts")
COLLECTION_CLEANED_POSTS = os.getenv("MONGO_COLLECTION_CLEANED", "cleaned_posts")
COLLECTION_POSTS_ANALYSIS = os.getenv("MONGO_COLLECTION_ANALYSIS", "posts_analysis")

# --- Scraping ---
SCRAPE_HASHTAG = os.getenv("SCRAPE_HASHTAG", "#Depression")
SCRAPE_MAX_POSTS = int(os.getenv("SCRAPE_MAX_POSTS", "100"))
SCRAPE_MIN_CHARS = int(os.getenv("SCRAPE_MIN_CHARS", "40"))
SCRAPE_MIN_WORDS = int(os.getenv("SCRAPE_MIN_WORDS", "5"))
SCRAPE_MAX_SCAN = int(os.getenv("SCRAPE_MAX_SCAN", "200"))

# --- API ---
API_HOST = os.getenv("API_HOST", "0.0.0.0")
API_PORT = int(os.getenv("API_PORT", "8000"))
