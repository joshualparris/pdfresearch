from __future__ import annotations

import hashlib
import re
import unicodedata
from collections.abc import Iterable

_ZERO_WIDTH = re.compile(r"[\u200b-\u200f\u202a-\u202e\u2060\ufeff]")
_WS = re.compile(r"\s+")
_PAGE_ONLY = re.compile(r"^(?:page\s*)?(\d{1,5})(?:\s*(?:of|/|\|)\s*\d{1,5})?\.?$", re.I)
_PAGE_ANYWHERE = re.compile(
    r"(?:\bpage\s+|\bp\.?\s*)(\d{1,5})(?:\s*(?:of|/)\s*\d{1,5})?\b",
    re.I,
)


def clean_line(value: str) -> str:
    value = unicodedata.normalize("NFKC", value or "")
    value = _ZERO_WIDTH.sub("", value)
    value = _WS.sub(" ", value).strip()
    return value


def normalise_text(value: str) -> str:
    """Aggressive but deterministic normalisation for *exact-content* page dedupe.

    We intentionally preserve words and numbers. Whitespace, Unicode presentation
    differences, and line wrapping are ignored. Case is folded. We do not remove
    page numbers because two otherwise-identical pages with different page numbers
    should remain distinct unless the caller deliberately opts into fuzzy dedupe.
    """
    value = unicodedata.normalize("NFKC", value or "")
    value = _ZERO_WIDTH.sub("", value)
    value = value.casefold()
    value = _WS.sub(" ", value).strip()
    return value


def sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8", errors="replace")).hexdigest()


def normalised_text_hash(value: str) -> str:
    return sha256_text(normalise_text(value))


def extract_page_number(lines: Iterable[str]) -> int | None:
    """Find an explicit printed page number, preferring footer/header-only forms."""
    cleaned = [clean_line(x) for x in lines if clean_line(x)]
    if not cleaned:
        return None

    edge = cleaned[:3] + cleaned[-4:]
    for line in reversed(edge):
        match = _PAGE_ONLY.match(line)
        if match:
            return int(match.group(1))
    for line in edge:
        match = _PAGE_ANYWHERE.search(line)
        if match:
            return int(match.group(1))
    return None


def strip_page_counter(line: str) -> str:
    line = clean_line(line)
    line = re.sub(r"\bpage\s+\d{1,5}(?:\s*(?:of|/)\s*\d{1,5})?\b", "", line, flags=re.I)
    line = re.sub(r"\b\d{1,5}\s*/\s*\d{1,5}\b", "", line)
    return clean_line(line)


def running_key(lines: Iterable[str], max_lines: int = 3) -> str:
    """Create a comparison key for repeated running headers/footers."""
    chosen: list[str] = []
    for raw in lines:
        line = strip_page_counter(raw)
        if not line:
            continue
        # Dates and raw URLs often make headers look unique despite same document.
        line = re.sub(r"https?://\S+", "<url>", line, flags=re.I)
        line = re.sub(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b", "<date>", line)
        line = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", "<date>", line)
        chosen.append(line.casefold())
        if len(chosen) >= max_lines:
            break
    return " | ".join(chosen)


def slugify(value: str, fallback: str = "untitled", max_len: int = 90) -> str:
    value = unicodedata.normalize("NFKD", value or "")
    value = "".join(ch for ch in value if not unicodedata.combining(ch))
    value = value.encode("ascii", "ignore").decode("ascii")
    value = value.casefold()
    value = re.sub(r"[^a-z0-9]+", "_", value).strip("_")
    if not value:
        value = fallback
    return value[:max_len].rstrip("_") or fallback


def similarity(a: str, b: str) -> float:
    """Cheap 0..1 token-overlap score without an extra dependency."""
    if not a and not b:
        return 1.0
    if not a or not b:
        return 0.0
    ta = set(re.findall(r"[a-z0-9]{2,}", a.casefold()))
    tb = set(re.findall(r"[a-z0-9]{2,}", b.casefold()))
    if not ta and not tb:
        return 1.0
    if not ta or not tb:
        return 0.0
    return len(ta & tb) / len(ta | tb)
