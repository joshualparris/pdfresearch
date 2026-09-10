from __future__ import annotations

from pdfresearch.config import Config
from pdfresearch.models import PageRecord
from pdfresearch.pipeline import build_segments
from pdfresearch.segment_first import build_segment_occurrences


def page(
    original_page: int,
    text_hash: str,
    *,
    duplicate_of: int | None = None,
) -> PageRecord:
    return PageRecord(
        original_page=original_page,
        text=f"synthetic page {original_page}",
        text_hash=text_hash,
        text_len=500,
        width=595,
        height=842,
        font_signature="synthetic",
        median_font_size=11,
        max_font_size=11,
        top_lines=["Synthetic report"],
        bottom_lines=[],
        header_key="synthetic report",
        footer_key="",
        page_number=None,
        title_candidate=None,
        duplicate_of=duplicate_of,
    )


def test_segment_first_retains_a_repeated_page_inside_one_document() -> None:
    records = [
        page(1, "a"),
        page(2, "b"),
        page(3, "b", duplicate_of=2),
        page(4, "c"),
    ]

    current, _ = build_segments(records, boundary_threshold=9999)
    safer, _ = build_segment_occurrences(records, boundary_threshold=9999)

    # Current dedupe-first behaviour removes page 3 before boundary inference.
    assert current[0].canonical_pages == [1, 2, 4]
    # Segment-first preserves the original source occurrence intact.
    assert safer[0].original_pages == [1, 2, 3, 4]


def test_segment_first_identifies_repeated_whole_document_after_splitting() -> None:
    records = [
        page(1, "a"),
        page(2, "b"),
        page(3, "c"),
        page(4, "a", duplicate_of=1),
        page(5, "b", duplicate_of=2),
        page(6, "c", duplicate_of=3),
    ]
    config = Config(force_boundary_before={4})

    current, _ = build_segments(records, boundary_threshold=9999, config=config)
    safer, _ = build_segment_occurrences(records, boundary_threshold=9999, config=config)

    # Dedupe-first erases the second occurrence, so the forced source boundary is
    # never even observed by the current production path.
    assert len(current) == 1

    assert len(safer) == 2
    assert safer[0].original_pages == [1, 2, 3]
    assert safer[1].original_pages == [4, 5, 6]
    assert safer[1].duplicate_of_segment_id == safer[0].segment_id
