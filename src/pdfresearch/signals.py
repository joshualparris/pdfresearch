from __future__ import annotations

import math
import re

from .models import BoundaryDecision, PageRecord
from .normalise import similarity

_FIRST_PAGE_CUES = re.compile(
    r"\b(?:executive\s+summary|research\s+report|deep\s+research|evidence\s+review|"
    r"prepared\s+for|prepared\s+by|final\s+report|comprehensive\s+report|"
    r"system\s+reference\s+document|table\s+of\s+contents|contents)\b",
    re.I,
)


def _geometry_distance(a: PageRecord, b: PageRecord) -> float:
    if not a.width or not a.height or not b.width or not b.height:
        return 0.0
    dw = abs(a.width - b.width) / max(a.width, b.width)
    dh = abs(a.height - b.height) / max(a.height, b.height)
    return max(dw, dh)


def score_boundary(prev: PageRecord, curr: PageRecord) -> BoundaryDecision:
    """Score whether ``curr`` begins a new source document.

    The weights are intentionally transparent, conservative, and easy to review.
    A caller should normally accept boundaries at >= 5.0, then inspect the
    near-threshold cases in boundary_review.csv.
    """
    score = 0.0
    reasons: list[str] = []

    gap = curr.original_page - prev.original_page
    if gap > 1:
        if gap >= 10:
            score += 3.0
            reasons.append(f"large_original_gap:{gap}")
        elif gap >= 4:
            score += 2.2
            reasons.append(f"duplicate_run_gap:{gap}")
        else:
            score += 1.0
            reasons.append(f"small_original_gap:{gap}")

    # Blank/separator page followed by content is a strong document-start cue.
    if prev.near_blank and not curr.near_blank:
        score += 2.0
        reasons.append("after_near_blank")

    geom = _geometry_distance(prev, curr)
    if geom >= 0.08:
        score += 2.2
        reasons.append("major_page_geometry_change")
    elif geom >= 0.025:
        score += 1.0
        reasons.append("page_geometry_change")

    # Printed page numbers are unusually useful in merged reports.
    if prev.page_number is not None and curr.page_number is not None:
        if curr.page_number == prev.page_number + 1:
            score -= 1.5
            reasons.append("page_number_continues")
        elif curr.page_number <= 2 and prev.page_number >= 3:
            score += 2.4
            reasons.append("page_number_resets")
        elif curr.page_number <= prev.page_number:
            score += 1.1
            reasons.append("page_number_goes_back")

    header_sim = similarity(prev.header_key, curr.header_key)
    if prev.header_key and curr.header_key:
        if header_sim >= 0.72:
            score -= 1.7
            reasons.append("running_header_continues")
        elif header_sim <= 0.12:
            score += 1.4
            reasons.append("running_header_changes")
        elif header_sim <= 0.30:
            score += 0.7
            reasons.append("running_header_weak_match")

    footer_sim = similarity(prev.footer_key, curr.footer_key)
    if prev.footer_key and curr.footer_key:
        if footer_sim >= 0.80:
            score -= 0.5
            reasons.append("running_footer_continues")
        elif footer_sim <= 0.10:
            score += 0.35
            reasons.append("running_footer_changes")

    if prev.font_signature and curr.font_signature and prev.font_signature != curr.font_signature:
        score += 0.55
        reasons.append("font_signature_changes")

    if curr.title_candidate:
        ratio = curr.max_font_size / max(curr.median_font_size, 1.0)
        if curr.max_font_size >= 18 and ratio >= 1.45:
            score += 1.7
            reasons.append("strong_title_typography")
        elif curr.max_font_size >= 14 and ratio >= 1.25:
            score += 0.8
            reasons.append("title_typography")

        if _FIRST_PAGE_CUES.search(curr.title_candidate):
            score += 1.4
            reasons.append("first_page_lexical_cue")

    # A very short current page with title typography often represents a cover.
    if curr.text_len < 1200 and curr.max_font_size >= 20 and curr.title_candidate:
        score += 0.7
        reasons.append("cover_like_page")

    # Conversely, uninterrupted body pages with very similar dimensions, headers,
    # and consecutive original numbering should resist accidental splits.
    if gap == 1 and geom < 0.01 and header_sim >= 0.72:
        score -= 0.4
        reasons.append("strong_continuity_bundle")

    # Keep score stable and readable in manifests.
    score = round(score, 3)
    if math.isclose(score, -0.0):
        score = 0.0
    return BoundaryDecision(
        before_original_page=curr.original_page,
        score=score,
        reasons=reasons,
        accepted=False,
    )
