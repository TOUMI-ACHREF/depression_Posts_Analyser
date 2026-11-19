"""
Nettoyage / normalisation de texte (couche silver).

- Supprime URLs, mentions @, emojis, caractères de contrôle
- Normalise unicode, casse, espaces
- Conserve le mot des hashtags sans le '#'
"""

from __future__ import annotations

import re
import unicodedata
from typing import Any

URL_RE = re.compile(
    r"(https?://\S+|www\.\S+|t\.co/\S+)",
    re.IGNORECASE,
)
MENTION_RE = re.compile(r"@\w+")
HASHTAG_RE = re.compile(r"#(\w+)")
# Blocs emoji / pictographes courants
EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001F9FF"
    "\U0001FA00-\U0001FAFF"
    "\U00002700-\U000027BF"
    "\U00002600-\U000026FF"
    "\U0001F1E0-\U0001F1FF"
    "\U0000200D"
    "\U0000FE0F"
    "]+",
    flags=re.UNICODE,
)
CONTROL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
# Ponctuation répétée / symboles isolés
MULTI_PUNCT_RE = re.compile(r"([!?.,;:]){2,}")
NON_WORD_SYMBOLS_RE = re.compile(r"[^\w\s'\-]", re.UNICODE)
WHITESPACE_RE = re.compile(r"\s+")

CLEANER_VERSION = "1.0.0"


def remove_urls(text: str) -> str:
    return URL_RE.sub(" ", text)


def remove_mentions(text: str) -> str:
    return MENTION_RE.sub(" ", text)


def normalize_hashtags(text: str) -> str:
    """#Depression → Depression (garde le token)."""
    return HASHTAG_RE.sub(r"\1", text)


def remove_emojis(text: str) -> str:
    return EMOJI_RE.sub(" ", text)


def normalize_unicode(text: str) -> str:
    return unicodedata.normalize("NFKC", text)


def normalize_whitespace(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def clean_text(text: str | None, *, lowercase: bool = True) -> str:
    """Pipeline complet de nettoyage + normalisation."""
    if not text:
        return ""

    out = normalize_unicode(text)
    out = remove_urls(out)
    out = remove_mentions(out)
    out = normalize_hashtags(out)
    out = remove_emojis(out)
    out = CONTROL_RE.sub(" ", out)
    out = MULTI_PUNCT_RE.sub(r"\1", out)
    out = NON_WORD_SYMBOLS_RE.sub(" ", out)
    if lowercase:
        out = out.lower()
    out = normalize_whitespace(out)
    return out


def clean_payload(text: str | None, *, lowercase: bool = True) -> dict[str, Any]:
    """Résultat détaillé pour l'API / debug."""
    original = text or ""
    cleaned = clean_text(original, lowercase=lowercase)
    return {
        "original_text": original,
        "cleaned_text": cleaned,
        "cleaner_version": CLEANER_VERSION,
        "stats": {
            "original_len": len(original),
            "cleaned_len": len(cleaned),
            "original_words": len(original.split()) if original else 0,
            "cleaned_words": len(cleaned.split()) if cleaned else 0,
        },
    }
