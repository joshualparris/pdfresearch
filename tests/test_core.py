from __future__ import annotations

from pathlib import Path

import fitz

from pdfresearch.config import Config
from pdfresearch.models import PageRecord
from pdfresearch.normalise import extract_page_number, normalise_text, similarity, slugify
from pdfresearch.pipeline import build_segments, scan_pdf
from pdfresearch.privacy import detect_privacy_flags
from pdfresearch.signals import score_boundary


def record(page: int, *, printed: int | None, header: str, title: str | None = None) -> PageRecord:
    return PageRecord(
        original_page=page,
        text=title or "body",
        text_hash=str(page),
        text_len=1000,
        width=595,
        height=842,
        font_signature="same-font",
        median_font_size=10,
        max_font_size=22 if title else 10,
        top_lines=[header],
        bottom_lines=[f"Page {printed}"] if printed is not None else [],
        header_key=header.casefold(),
        footer_key="",
        page_number=printed,
        title_candidate=title,
    )


def test_normalisation_and_slugify() -> None:
    assert normalise_text("  Hello\nWORLD  ") == "hello world"
    assert slugify("Josh's — Report 2026") == "josh_s_report_2026"
    assert similarity("alpha beta gamma", "alpha beta") > 0.6


def test_page_number_extraction() -> None:
    assert extract_page_number(["Report title", "Page 12 of 40"]) == 12
    assert extract_page_number(["Report title", "13/40"]) == 13
    assert extract_page_number(["No page counter here"]) is None


def test_privacy_detector_returns_categories_not_values() -> None:
    fake = "Email person@example.com, phone 0412 345 678, BSB 123-456. NDIS number 123456789."
    flags = detect_privacy_flags(fake)
    assert "email" in flags
    assert "australian_phone" in flags
    assert "bsb" in flags
    assert "ndis_context" in flags
    joined = " ".join(flags)
    assert "person@example.com" not in joined
    assert "0412" not in joined


def test_boundary_score_likes_page_reset_and_title() -> None:
    prev = record(20, printed=18, header="Old Report")
    curr = record(21, printed=1, header="New Research Report", title="New Research Report")
    decision = score_boundary(prev, curr)
    assert decision.score > 0
    assert "page_number_resets" in decision.reasons
    assert "strong_title_typography" in decision.reasons


def _make_synthetic_pdf(path: Path) -> None:
    doc = fitz.open()
    try:
        pages = [
            ("Report A", 24),
            ("A body page\nPage 2 of 2", 11),
            ("A body page\nPage 2 of 2", 11),  # exact text duplicate
            ("Report B", 24),
            ("B body page\nPage 2 of 2", 11),
        ]
        for text, size in pages:
            page = doc.new_page(width=595, height=842)
            page.insert_text((72, 90), text, fontsize=size)
        doc.save(path)
    finally:
        doc.close()


def test_end_to_end_scan_dedup_and_forced_split(tmp_path: Path) -> None:
    pdf = tmp_path / "synthetic.pdf"
    out = tmp_path / "out"
    _make_synthetic_pdf(pdf)

    records = scan_pdf(pdf, out, min_text_for_text_hash=5, progress_every=0)
    assert len(records) == 5
    assert sum(r.duplicate_of is not None for r in records) == 1
    assert records[2].duplicate_of == 2

    config = Config(force_boundary_before={4})
    segments, decisions = build_segments(records, boundary_threshold=9999, config=config)
    assert len(segments) == 2
    assert segments[0].canonical_pages == [1, 2]
    assert segments[1].canonical_pages == [4, 5]
    assert any(d.before_original_page == 4 and d.accepted for d in decisions)
