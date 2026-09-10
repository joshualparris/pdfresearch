from __future__ import annotations

import re
from collections.abc import Iterable

# These are intentionally conservative. The report records only the category and
# page number; matched values are never emitted.
_PATTERN_FLAGS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"\b[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}\b", re.I)),
    ("australian_phone", re.compile(r"(?<!\d)(?:\+?61\s?[2-478]|0[2-478])(?:[\s-]?\d){8}(?!\d)")),
    ("bsb", re.compile(r"\b\d{3}[- ]\d{3}\b")),
    ("vin", re.compile(r"\b[A-HJ-NPR-Z0-9]{17}\b")),
    ("medicare_context", re.compile(r"\bmedicare\b.{0,50}\b\d{8,12}\b", re.I | re.S)),
    ("ndis_context", re.compile(r"\bndis\b.{0,80}\b\d{7,12}\b", re.I | re.S)),
    ("tfn_context", re.compile(r"\b(?:tfn|tax\s+file\s+number)\b.{0,50}\b\d(?:[\s-]?\d){7,8}\b", re.I | re.S)),
    ("bank_account_context", re.compile(r"\b(?:account\s*(?:number|no\.?|#)|acct)\b.{0,40}\b\d{5,12}\b", re.I | re.S)),
    ("drivers_licence_context", re.compile(r"\b(?:driver'?s?\s+licen[cs]e|licen[cs]e\s+no\.?)\b.{0,60}\b[A-Z0-9-]{5,16}\b", re.I | re.S)),
    ("date_of_birth_context", re.compile(r"\b(?:date\s+of\s+birth|dob)\b", re.I)),
    ("street_address_context", re.compile(r"\b\d{1,5}\s+[A-Za-z][A-Za-z .'-]{2,40}\s(?:street|st|road|rd|avenue|ave|drive|dr|lane|ln|court|ct|place|pl|way|crescent|cres|boulevard|blvd)\b", re.I)),
]


def detect_privacy_flags(text: str) -> list[str]:
    flags = {name for name, pattern in _PATTERN_FLAGS if pattern.search(text or "")}
    return sorted(flags)


def merge_flags(flag_groups: Iterable[Iterable[str]]) -> list[str]:
    merged: set[str] = set()
    for group in flag_groups:
        merged.update(group)
    return sorted(merged)
