"""Filtre qualité scrape : ignore posts média / hashtags seuls."""

from __future__ import annotations

import re

NON_TEXT_LANGS = {"qme", "qht", "zxx", "und"}
URL_RE = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
MENTION_RE = re.compile(r"@\w+")
HASHTAG_RE = re.compile(r"#\w+")
WHITESPACE_RE = re.compile(r"\s+")


def extract_plain_text(text: str | None) -> str:
    """Retire URLs, @mentions et #hashtags pour juger s'il reste du texte utile."""
    if not text:
        return ""
    cleaned = URL_RE.sub(" ", text)
    cleaned = MENTION_RE.sub(" ", cleaned)
    cleaned = HASHTAG_RE.sub(" ", cleaned)
    return WHITESPACE_RE.sub(" ", cleaned).strip()


def has_meaningful_text(
    text: str | None,
    lang: str | None = None,
    min_chars: int = 40,
    min_words: int = 5,
) -> bool:
    plain = extract_plain_text(text)
    if len(plain) < min_chars:
        return False
    if len(plain.split()) < min_words:
        return False
    if (lang or "").lower() in NON_TEXT_LANGS and len(plain) < min_chars * 2:
        return False
    return True
