from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Sequence

from .config import Config
from .models import BoundaryDecision, PageRecord
from .pipeline import build_segments, scan_pdf
from .signals import score_boundary


@dataclass(slots=True)
class SegmentOccurrence:
    """One source-document occurrence in the original page stream.

    This intentionally retains pages that were previously seen elsewhere. Exact page
    duplicates are evidence during boundary inference; they are not removed first.
    """

    segment_id: int
    original_pages: list[int]
    fingerprint: str
    duplicate_of_segment_id: int | None
    boundary_score: float
    boundary_reasons: list[str]

    @property
    def page_count(self) -> int:
        return len(self.original_pages)

    @property
    def original_start(self) -> int:
        return self.original_pages[0] if self.original_pages else 0

    @property
    def original_end(self) -> int:
        return self.original_pages[-1] if self.original_pages else 0

    def to_json(self) -> dict[str, object]:
        data = asdict(self)
        data["page_count"] = self.page_count
        data["original_start"] = self.original_start
        data["original_end"] = self.original_end
        # A prefix is enough for a review manifest and avoids pretending this is a
        # user-facing identifier with long-term stability guarantees.
        data["fingerprint"] = self.fingerprint[:20]
        return data


def _segment_fingerprint(pages: Sequence[PageRecord]) -> str:
    material = "segment-v1\0" + "\0".join(page.text_hash for page in pages)
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _apply_overrides(decision: BoundaryDecision, config: Config) -> BoundaryDecision:
    page = decision.before_original_page
    if page in config.force_boundary_before:
        decision.score = max(decision.score, 999.0)
        decision.reasons.append("forced_by_config")
        decision.accepted = True
    elif page in config.suppress_boundary_before:
        decision.score = min(decision.score, -999.0)
        decision.reasons.append("suppressed_by_config")
        decision.accepted = False
    return decision


def build_segment_occurrences(
    records: Sequence[PageRecord],
    *,
    boundary_threshold: float = 5.0,
    config: Config | None = None,
) -> tuple[list[SegmentOccurrence], list[BoundaryDecision]]:
    """Segment the *original* page stream, then mark exact duplicate segments.

    This is an audit companion to the current production `build_segments()` path.
    Its purpose is to test the architectural alternative described in REVIEW.md:

      1. detect page duplicates but retain all pages for boundary inference;
      2. segment the original stream;
      3. detect exact duplicate document occurrences afterwards.

    No extracted page text is written by this module.
    """

    config = config or Config()
    stream = list(records)
    if not stream:
        return [], []

    groups: list[tuple[BoundaryDecision, list[PageRecord]]] = []
    decisions: list[BoundaryDecision] = []
    start = BoundaryDecision(
        before_original_page=stream[0].original_page,
        score=999.0,
        reasons=["corpus_start"],
        accepted=True,
    )
    current: list[PageRecord] = [stream[0]]
    current_start = start

    for prev, curr in zip(stream, stream[1:]):
        decision = score_boundary(prev, curr)
        decision.accepted = decision.score >= boundary_threshold
        decision = _apply_overrides(decision, config)
        decisions.append(decision)
        if decision.accepted:
            groups.append((current_start, current))
            current = [curr]
            current_start = decision
        else:
            current.append(curr)
    groups.append((current_start, current))

    seen_segments: dict[str, int] = {}
    occurrences: list[SegmentOccurrence] = []
    for segment_id, (boundary, pages) in enumerate(groups, start=1):
        fingerprint = _segment_fingerprint(pages)
        duplicate_of = seen_segments.get(fingerprint)
        if duplicate_of is None:
            seen_segments[fingerprint] = segment_id
        occurrences.append(
            SegmentOccurrence(
                segment_id=segment_id,
                original_pages=[page.original_page for page in pages],
                fingerprint=fingerprint,
                duplicate_of_segment_id=duplicate_of,
                boundary_score=boundary.score,
                boundary_reasons=list(boundary.reasons),
            )
        )

    return occurrences, decisions


def run_segment_first_audit(
    source: str | Path,
    output_dir: str | Path,
    *,
    boundary_threshold: float = 5.0,
    min_text_for_text_hash: int = 80,
    config_path: str | Path | None = None,
    rescan: bool = False,
) -> dict[str, object]:
    """Run both segmentation orders and write a metadata-only comparison manifest."""

    source = Path(source)
    output_dir = Path(output_dir)
    manifest_dir = output_dir / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)
    config = Config.load(config_path)

    records = scan_pdf(
        source,
        output_dir,
        min_text_for_text_hash=min_text_for_text_hash,
        rescan=rescan,
    )
    current_segments, _ = build_segments(
        records,
        boundary_threshold=boundary_threshold,
        config=config,
    )
    occurrences, decisions = build_segment_occurrences(
        records,
        boundary_threshold=boundary_threshold,
        config=config,
    )

    duplicate_occurrences = [
        item for item in occurrences if item.duplicate_of_segment_id is not None
    ]
    result: dict[str, object] = {
        "source_page_count": len(records),
        "page_duplicates_detected": sum(
            1 for record in records if record.duplicate_of is not None
        ),
        "dedupe_first_segment_count": len(current_segments),
        "segment_first_occurrence_count": len(occurrences),
        "segment_first_unique_document_count": len(occurrences) - len(duplicate_occurrences),
        "segment_first_exact_duplicate_occurrences": len(duplicate_occurrences),
        "accepted_boundaries": sum(1 for item in decisions if item.accepted),
        "segments": [item.to_json() for item in occurrences],
    }

    path = manifest_dir / "segment_first_audit.json"
    path.write_text(json.dumps(result, indent=2), encoding="utf-8")
    return result
