from __future__ import annotations

import re
from dataclasses import dataclass

from .normalise import clean_line, slugify


@dataclass(frozen=True, slots=True)
class Classification:
    category: str
    reason: str


_REFERENCE_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("tolkien", re.compile(r"\b(?:the\s+hobbit|the\s+lord\s+of\s+the\s+rings|fellowship\s+of\s+the\s+ring|two\s+towers|return\s+of\s+the\s+king|j\.?\s*r\.?\s*r\.?\s+tolkien)\b", re.I)),
    ("psalms", re.compile(r"\b(?:scottish\s+psalter|sing\s+psalms|metrical\s+psalter|book\s+of\s+psalms|constable'?s\s+notes\s+on\s+psalms)\b", re.I)),
    ("deep_learning_textbook", re.compile(r"\bdeep\s+learning\b.{0,120}\b(?:goodfellow|bengio|courville)\b", re.I | re.S)),
    ("dnd_srd", re.compile(r"\b(?:system\s+reference\s+document|srd\s*5(?:\.1)?|dungeons\s*&?\s*dragons)\b", re.I)),
    ("linux_study_guide", re.compile(r"\b(?:lpic[- ]?1|linux\+|comptia\s+linux|linux\s+professional\s+institute)\b", re.I)),
    ("academic_publication", re.compile(r"\b(?:doi:\s*10\.|journal\s+of\s+|doctoral\s+thesis|phd\s+thesis|master'?s\s+thesis)\b", re.I)),
    ("legal_publication", re.compile(r"\b(?:supreme\s+court\s+of\s+the\s+united\s+states|u\.s\.\s+supreme\s+court|law\s+review|united\s+nations\s+security\s+council)\b", re.I)),
]

_TITLE_NOISE = re.compile(
    r"^(?:page\s+\d+|\d+\s*/\s*\d+|contents|table\s+of\s+contents|copyright|confidential)$",
    re.I,
)


def classify_segment(text_sample: str) -> Classification:
    sample = text_sample[:30_000]
    for label, pattern in _REFERENCE_RULES:
        if pattern.search(sample):
            return Classification("reference", label)
    return Classification("personal", "no_reference_rule_matched")


def choose_title(candidates: list[str], text_sample: str, segment_id: int) -> str:
    """Pick a human-readable title without relying on an external model."""
    for raw in candidates:
        line = clean_line(raw)
        if not line or len(line) < 4 or len(line) > 180:
            continue
        if _TITLE_NOISE.match(line):
            continue
        if re.match(r"^https?://", line, re.I):
            continue
        return line

    for raw in text_sample.splitlines()[:30]:
        line = clean_line(raw)
        if 4 <= len(line) <= 180 and not _TITLE_NOISE.match(line):
            return line

    return f"Untitled segment {segment_id:04d}"


def make_slug(title: str, segment_id: int) -> str:
    return slugify(title, fallback=f"segment_{segment_id:04d}")
