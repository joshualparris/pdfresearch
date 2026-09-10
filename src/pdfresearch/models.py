from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(slots=True)
class PageRecord:
    original_page: int
    text: str
    text_hash: str
    text_len: int
    width: float
    height: float
    font_signature: str
    font_names: list[str] = field(default_factory=list)
    median_font_size: float = 0.0
    max_font_size: float = 0.0
    top_lines: list[str] = field(default_factory=list)
    bottom_lines: list[str] = field(default_factory=list)
    header_key: str = ""
    footer_key: str = ""
    page_number: int | None = None
    title_candidate: str | None = None
    image_fingerprint: str = ""
    near_blank: bool = False
    privacy_flags: list[str] = field(default_factory=list)
    duplicate_of: int | None = None

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_json(cls, data: dict[str, Any]) -> "PageRecord":
        return cls(**data)


@dataclass(slots=True)
class BoundaryDecision:
    before_original_page: int
    score: float
    reasons: list[str] = field(default_factory=list)
    accepted: bool = False

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class Segment:
    segment_id: int
    title: str
    slug: str
    category: str
    category_reason: str
    original_pages: list[int]
    canonical_pages: list[int]
    boundary_score: float
    boundary_reasons: list[str]

    @property
    def page_count(self) -> int:
        return len(self.canonical_pages)

    @property
    def original_start(self) -> int:
        return min(self.original_pages) if self.original_pages else 0

    @property
    def original_end(self) -> int:
        return max(self.original_pages) if self.original_pages else 0

    def to_json(self) -> dict[str, Any]:
        data = asdict(self)
        data["page_count"] = self.page_count
        data["original_start"] = self.original_start
        data["original_end"] = self.original_end
        return data
