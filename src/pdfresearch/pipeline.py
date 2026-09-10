from __future__ import annotations

import csv
import hashlib
import json
import os
import re
import statistics
from collections import defaultdict
from dataclasses import replace
from pathlib import Path
from typing import Iterable, Sequence

import fitz  # PyMuPDF

from .classifier import choose_title, classify_segment, make_slug
from .config import Config
from .models import BoundaryDecision, PageRecord, Segment
from .normalise import (
    clean_line,
    extract_page_number,
    normalise_text,
    running_key,
    sha256_text,
)
from .privacy import detect_privacy_flags
from .pdf_links import file_spec_value, is_relative_file
from .signals import score_boundary


CACHE_SCHEMA_VERSION = 1


def _hash_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _source_identity(path: Path, min_text_for_text_hash: int) -> dict[str, object]:
    stat = path.stat()
    return {
        "cache_schema_version": CACHE_SCHEMA_VERSION,
        "source_path": str(path.resolve()),
        "source_size": stat.st_size,
        "source_mtime_ns": stat.st_mtime_ns,
        "min_text_for_text_hash": min_text_for_text_hash,
    }


def _extract_page_features(
    doc: fitz.Document,
    page: fitz.Page,
    page_number_1based: int,
    min_text_for_text_hash: int,
    image_hash_cache: dict[int, str],
) -> PageRecord:
    raw = page.get_text("dict", sort=True)
    lines: list[tuple[float, float, str, float]] = []
    font_names: set[str] = set()
    font_sizes: list[float] = []

    for block in raw.get("blocks", []):
        if block.get("type") != 0:
            continue
        for line in block.get("lines", []):
            spans = line.get("spans", [])
            text = clean_line("".join(str(span.get("text", "")) for span in spans))
            if not text:
                continue
            bbox = line.get("bbox", (0, 0, 0, 0))
            y0 = float(bbox[1])
            y1 = float(bbox[3])
            sizes = [float(span.get("size", 0.0) or 0.0) for span in spans]
            line_max_size = max(sizes, default=0.0)
            lines.append((y0, y1, text, line_max_size))
            for span in spans:
                font = str(span.get("font", "") or "")
                if font:
                    font_names.add(font)
                size = float(span.get("size", 0.0) or 0.0)
                if size > 0:
                    font_sizes.append(size)

    text_lines = [line[2] for line in lines]
    text = "\n".join(text_lines)
    normalized = normalise_text(text)
    width = float(page.rect.width)
    height = float(page.rect.height)

    top_lines = [text for y0, y1, text, _ in lines if y1 <= height * 0.20][:6]
    bottom_lines = [text for y0, y1, text, _ in lines if y0 >= height * 0.80][-6:]

    median_font = statistics.median(font_sizes) if font_sizes else 0.0
    max_font = max(font_sizes, default=0.0)
    font_material = "|".join(sorted(font_names)) + "::" + "|".join(
        str(round(x, 1)) for x in sorted(set(font_sizes))
    )
    font_signature = sha256_text(font_material)[:20] if font_material else ""

    title_candidate: str | None = None
    top_title_lines = [row for row in lines if row[0] <= height * 0.38 and 4 <= len(row[2]) <= 180]
    if top_title_lines:
        # Typography first, then vertical position. This is deterministic and reviewable.
        best = max(top_title_lines, key=lambda row: (row[3], -row[0], len(row[2])))
        if best[3] >= max(14.0, median_font * 1.20):
            title_candidate = best[2]

    near_blank = len(normalized) < min_text_for_text_hash
    image_fingerprint = ""
    if near_blank:
        image_hashes: list[str] = []
        try:
            for image in page.get_images(full=True):
                xref = int(image[0])
                if xref not in image_hash_cache:
                    try:
                        payload = doc.extract_image(xref).get("image", b"")
                    except Exception:
                        payload = b""
                    image_hash_cache[xref] = _hash_bytes(payload) if payload else f"xref:{xref}"
                image_hashes.append(image_hash_cache[xref])
        except Exception:
            image_hashes = []
        if image_hashes:
            image_fingerprint = sha256_text("|".join(sorted(image_hashes)))[:24]

    if len(normalized) >= min_text_for_text_hash:
        page_hash = sha256_text(normalized)
    else:
        # Near-blank pages need more than a tiny text string to avoid false dedupe.
        structural = json.dumps(
            {
                "text": normalized,
                "w": round(width, 2),
                "h": round(height, 2),
                "font": font_signature,
                "images": image_fingerprint,
            },
            sort_keys=True,
            ensure_ascii=True,
        )
        page_hash = sha256_text(structural)

    return PageRecord(
        original_page=page_number_1based,
        text=text,
        text_hash=page_hash,
        text_len=len(normalized),
        width=width,
        height=height,
        font_signature=font_signature,
        font_names=sorted(font_names),
        median_font_size=round(float(median_font), 3),
        max_font_size=round(float(max_font), 3),
        top_lines=top_lines,
        bottom_lines=bottom_lines,
        header_key=running_key(top_lines),
        footer_key=running_key(reversed(bottom_lines)),
        page_number=extract_page_number(text_lines),
        title_candidate=title_candidate,
        image_fingerprint=image_fingerprint,
        near_blank=near_blank,
        privacy_flags=detect_privacy_flags(text),
    )


def scan_pdf(
    source: str | Path,
    output_dir: str | Path,
    *,
    min_text_for_text_hash: int = 80,
    rescan: bool = False,
    progress_every: int = 250,
) -> list[PageRecord]:
    """Scan all pages, assign exact duplicate links, and persist a resumable JSONL cache."""
    source = Path(source)
    output_dir = Path(output_dir)
    cache_dir = output_dir / ".cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    pages_cache = cache_dir / "pages.jsonl"
    source_cache = cache_dir / "source.json"
    identity = _source_identity(source, min_text_for_text_hash)

    if rescan:
        pages_cache.unlink(missing_ok=True)
        source_cache.unlink(missing_ok=True)

    existing: list[PageRecord] = []
    if pages_cache.exists() and source_cache.exists():
        try:
            cached_identity = json.loads(source_cache.read_text(encoding="utf-8"))
        except Exception:
            cached_identity = None
        if cached_identity == identity:
            with pages_cache.open("r", encoding="utf-8") as handle:
                for line in handle:
                    line = line.strip()
                    if line:
                        existing.append(PageRecord.from_json(json.loads(line)))
        else:
            pages_cache.unlink(missing_ok=True)
            source_cache.unlink(missing_ok=True)

    source_cache.write_text(json.dumps(identity, indent=2), encoding="utf-8")

    doc = fitz.open(source)
    try:
        total = doc.page_count
        if len(existing) > total:
            raise RuntimeError("Cache contains more pages than the current PDF. Re-run with --rescan.")

        seen_hash: dict[str, int] = {}
        for record in existing:
            if record.duplicate_of is None:
                seen_hash.setdefault(record.text_hash, record.original_page)

        image_hash_cache: dict[int, str] = {}
        records = list(existing)
        mode = "a" if existing else "w"
        with pages_cache.open(mode, encoding="utf-8") as handle:
            for index in range(len(existing), total):
                page = doc.load_page(index)
                record = _extract_page_features(
                    doc,
                    page,
                    index + 1,
                    min_text_for_text_hash,
                    image_hash_cache,
                )
                canonical = seen_hash.get(record.text_hash)
                if canonical is not None:
                    record.duplicate_of = canonical
                else:
                    seen_hash[record.text_hash] = record.original_page

                records.append(record)
                handle.write(json.dumps(record.to_json(), ensure_ascii=False) + "\n")
                if (index + 1) % 100 == 0:
                    handle.flush()
                if progress_every and ((index + 1) % progress_every == 0 or index + 1 == total):
                    unique = sum(1 for item in records if item.duplicate_of is None)
                    print(f"scanned {index + 1:,}/{total:,} pages; unique {unique:,}; duplicates {len(records)-unique:,}")
        return records
    finally:
        doc.close()


def _apply_boundary_overrides(decision: BoundaryDecision, config: Config) -> BoundaryDecision:
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


def build_segments(
    records: Sequence[PageRecord],
    *,
    boundary_threshold: float = 5.0,
    config: Config | None = None,
) -> tuple[list[Segment], list[BoundaryDecision]]:
    config = config or Config()
    canonical = [record for record in records if record.duplicate_of is None]
    if not canonical:
        return [], []

    decisions: list[BoundaryDecision] = []
    groups: list[tuple[BoundaryDecision, list[PageRecord]]] = []
    start_decision = BoundaryDecision(
        before_original_page=canonical[0].original_page,
        score=999.0,
        reasons=["corpus_start"],
        accepted=True,
    )
    current: list[PageRecord] = [canonical[0]]
    current_start = start_decision

    for prev, curr in zip(canonical, canonical[1:]):
        decision = score_boundary(prev, curr)
        decision.accepted = decision.score >= boundary_threshold
        decision = _apply_boundary_overrides(decision, config)
        decisions.append(decision)
        if decision.accepted:
            groups.append((current_start, current))
            current = [curr]
            current_start = decision
        else:
            current.append(curr)
    groups.append((current_start, current))

    segments: list[Segment] = []
    used_slugs: set[str] = set()
    for seg_id, (boundary, pages) in enumerate(groups, start=1):
        sample_pages = pages[:4]
        sample = "\n\n".join(page.text for page in sample_pages)[:60_000]
        first_page = pages[0].original_page
        candidates: list[str] = []
        for page in sample_pages:
            if page.title_candidate:
                candidates.append(page.title_candidate)
            candidates.extend(page.top_lines[:3])

        title = config.title_overrides.get(first_page) or choose_title(candidates, sample, seg_id)
        slug = make_slug(title, seg_id)
        if slug in used_slugs:
            slug = f"{slug}_{seg_id:04d}"
        used_slugs.add(slug)

        override = config.classify_override(sample)
        if override:
            category, category_reason = override
        else:
            classification = classify_segment(sample)
            category, category_reason = classification.category, classification.reason

        if first_page in config.category_overrides:
            category = config.category_overrides[first_page]
            category_reason = "config_page_category_override"

        canonical_pages = [page.original_page for page in pages]
        segments.append(
            Segment(
                segment_id=seg_id,
                title=title,
                slug=slug,
                category=category,
                category_reason=category_reason,
                original_pages=list(canonical_pages),
                canonical_pages=list(canonical_pages),
                boundary_score=boundary.score,
                boundary_reasons=list(boundary.reasons),
            )
        )
    return segments, decisions


def _page_ranges(pages: Iterable[int]) -> str:
    values = sorted(set(pages))
    if not values:
        return ""
    runs: list[str] = []
    start = prev = values[0]
    for value in values[1:]:
        if value == prev + 1:
            prev = value
            continue
        runs.append(str(start) if start == prev else f"{start}-{prev}")
        start = prev = value
    runs.append(str(start) if start == prev else f"{start}-{prev}")
    return ";".join(runs)


def _contiguous_runs(pages: Iterable[int]) -> list[tuple[int, int]]:
    values = sorted(set(pages))
    if not values:
        return []
    runs: list[tuple[int, int]] = []
    start = prev = values[0]
    for value in values[1:]:
        if value == prev + 1:
            prev = value
            continue
        runs.append((start, prev))
        start = prev = value
    runs.append((start, prev))
    return runs


def write_manifests(
    output_dir: str | Path,
    records: Sequence[PageRecord],
    segments: Sequence[Segment],
    decisions: Sequence[BoundaryDecision],
) -> dict[str, object]:
    output_dir = Path(output_dir)
    manifest_dir = output_dir / "manifests"
    manifest_dir.mkdir(parents=True, exist_ok=True)

    canonical_to_segment: dict[int, int] = {}
    for segment in segments:
        for page in segment.canonical_pages:
            canonical_to_segment[page] = segment.segment_id

    with (manifest_dir / "segments.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "segment_id", "title", "category", "category_reason", "page_count",
            "original_start", "original_end", "canonical_page_ranges",
            "boundary_score", "boundary_reasons",
        ])
        for segment in segments:
            writer.writerow([
                segment.segment_id,
                segment.title,
                segment.category,
                segment.category_reason,
                segment.page_count,
                segment.original_start,
                segment.original_end,
                _page_ranges(segment.canonical_pages),
                segment.boundary_score,
                "|".join(segment.boundary_reasons),
            ])

    (manifest_dir / "segments.json").write_text(
        json.dumps([segment.to_json() for segment in segments], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    duplicate_groups: dict[int, list[int]] = defaultdict(list)
    with (manifest_dir / "page_map.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow([
            "original_page", "canonical_page", "is_duplicate", "canonical_segment_id",
            "hash_prefix", "text_len", "near_blank", "privacy_flags",
        ])
        for record in records:
            canonical_page = record.duplicate_of or record.original_page
            if record.duplicate_of is not None:
                duplicate_groups[canonical_page].append(record.original_page)
            writer.writerow([
                record.original_page,
                canonical_page,
                record.duplicate_of is not None,
                canonical_to_segment.get(canonical_page, ""),
                record.text_hash[:16],
                record.text_len,
                record.near_blank,
                "|".join(record.privacy_flags),
            ])

    with (manifest_dir / "duplicate_groups.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["canonical_page", "duplicate_count", "duplicate_pages"])
        for canonical_page, duplicate_pages in sorted(duplicate_groups.items()):
            writer.writerow([canonical_page, len(duplicate_pages), _page_ranges(duplicate_pages)])

    with (manifest_dir / "boundary_review.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["before_original_page", "score", "accepted", "reasons"])
        for decision in decisions:
            writer.writerow([
                decision.before_original_page,
                decision.score,
                decision.accepted,
                "|".join(decision.reasons),
            ])

    with (manifest_dir / "privacy_flags.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["original_page", "is_duplicate", "privacy_flag_types"])
        for record in records:
            if record.privacy_flags:
                writer.writerow([
                    record.original_page,
                    record.duplicate_of is not None,
                    "|".join(record.privacy_flags),
                ])

    unique_count = sum(1 for record in records if record.duplicate_of is None)
    duplicate_count = len(records) - unique_count
    stats: dict[str, object] = {
        "total_pages": len(records),
        "unique_pages": unique_count,
        "duplicate_pages": duplicate_count,
        "duplicate_percentage": round((duplicate_count / len(records) * 100.0), 3) if records else 0.0,
        "segments": len(segments),
        "personal_segments": sum(1 for segment in segments if segment.category == "personal"),
        "reference_segments": sum(1 for segment in segments if segment.category == "reference"),
        "pages_with_privacy_flags": sum(1 for record in records if record.privacy_flags),
    }
    (manifest_dir / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    return stats


def _set_pdf_key(doc: fitz.Document, xref: int, key: str, value: str) -> None:
    """Set a nested key even when an intermediate dictionary is indirect."""
    parts = key.split("/")
    for index in range(1, len(parts)):
        prefix = "/".join(parts[:index])
        kind, target = doc.xref_get_key(xref, prefix)
        if kind == "xref":
            return _set_pdf_key(doc, int(target.split()[0]), "/".join(parts[index:]), value)
    doc.xref_set_key(xref, key, value)


def _write_segment_pdf(source_doc: fitz.Document, pages: Sequence[int], path: Path, title: str) -> None:
    # insert_pdf omits some page dictionary entries (including transparency
    # groups) and can drop orphan widget appearances in merged PDFs. Selecting
    # pages in a fresh copy retains those original objects without flattening.
    if source_doc.name and not source_doc.is_dirty and Path(source_doc.name).is_file():
        out = fitz.open(source_doc.name)
    else:
        out = fitz.open(stream=source_doc.tobytes(), filetype="pdf")
    try:
        selected = {page - 1 for page in pages}
        # A split cannot keep a local GoTo destination on an omitted page.
        # Preserve navigation with an explicit relative link to the source PDF.
        for page_number in pages:
            # Read the immutable source: several links may share one indirect
            # action/file specification, which must not be rebased repeatedly.
            for link in source_doc[page_number - 1].get_links():
                action = source_doc.xref_get_key(link["xref"], "A/S")[1]
                target_file = file_spec_value(source_doc, link["xref"], link.get("file", ""))
                if action in {"/Launch", "/GoToR"} and is_relative_file(target_file):
                    if not source_doc.name:
                        raise ValueError("Relative file links require a saved source PDF")
                    target = Path(source_doc.name).resolve().parent / target_file
                    relative = Path(os.path.relpath(target, path.parent.resolve())).as_posix()
                    kind, value = out.xref_get_key(link["xref"], "A/F")
                    is_dictionary = kind == "dict" or (
                        kind == "xref" and out.xref_object(int(value.split()[0])).lstrip().startswith("<<")
                    )
                    if is_dictionary:
                        _set_pdf_key(out, link["xref"], "A/F/F", fitz.get_pdf_str(relative))
                        _set_pdf_key(out, link["xref"], "A/F/UF", fitz.get_pdf_str(relative))
                    else:
                        _set_pdf_key(out, link["xref"], "A/F", fitz.get_pdf_str(relative))
                if link["kind"] != fitz.LINK_GOTO or link.get("page", -1) < 0:
                    continue
                if link["page"] in selected:
                    continue
                if not source_doc.name or not Path(source_doc.name).is_file():
                    raise ValueError("Cross-document links require a saved source PDF")
                destination_type, destination = out.xref_get_key(link["xref"], "A/D")
                if destination_type == "null":
                    destination_type, destination = out.xref_get_key(link["xref"], "Dest")
                if destination_type != "array":
                    raise ValueError("Cannot preserve an unresolved cross-document destination")
                destination, replacements = re.subn(
                    r"^\[\s*\d+\s+\d+\s+R", f"[{link['page']}", destination, count=1,
                )
                if replacements != 1:
                    raise ValueError("Unexpected cross-document destination array")
                relative = Path(os.path.relpath(Path(source_doc.name).resolve(), path.parent.resolve())).as_posix()
                # Keep the original destination's PDF coordinates / view mode.
                # get_links() loses that detail for several remote destinations.
                out.xref_set_key(link["xref"], "A", f"<</S/GoToR/D{destination}/F{fitz.get_pdf_str(relative)}>>")
                out.xref_set_key(link["xref"], "Dest", "null")
        out.select([page - 1 for page in pages])
        # select() drops unresolved named links even though they exist in the
        # original PDF. Keep their original annotation objects and original
        # (possibly already unresolved) behaviour instead of silently deleting.
        for offset, page_number in enumerate(pages):
            source_links = source_doc[page_number - 1].get_links()
            if not source_links:
                continue
            page_xref = out.page_xref(offset)
            kind, annotations = out.xref_get_key(page_xref, "Annots")
            if kind == "xref":
                annotations = out.xref_object(int(annotations.split()[0]))
            elif kind == "null":
                annotations = "[]"
            present = {int(x) for x in re.findall(r"(\d+)\s+\d+\s+R", annotations)}
            missing = [link["xref"] for link in source_links if link["xref"] not in present]
            if missing:
                if not annotations.rstrip().endswith("]"):
                    raise ValueError("Cannot preserve links in an invalid annotation array")
                annotations = annotations.rstrip()[:-1] + " " + " ".join(f"{xref} 0 R" for xref in missing) + "]"
                out.xref_set_key(page_xref, "Annots", annotations)
        metadata = out.metadata or {}
        metadata["title"] = title
        metadata["producer"] = "pdfresearch"
        out.set_metadata(metadata)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            path.unlink()
        out.save(path, garbage=3, deflate=True, clean=False)
    finally:
        out.close()


def write_split_outputs(
    source: str | Path,
    output_dir: str | Path,
    records: Sequence[PageRecord],
    segments: Sequence[Segment],
    *,
    write_pdfs: bool = True,
    write_text: bool = True,
    write_deduped_pdf: bool = False,
) -> None:
    output_dir = Path(output_dir)
    by_page = {record.original_page: record for record in records}
    source_doc = fitz.open(source) if (write_pdfs or write_deduped_pdf) else None
    try:
        for segment in segments:
            category_dir = output_dir / segment.category
            stem = f"{segment.segment_id:04d}_{segment.slug}"
            if write_pdfs and source_doc is not None:
                _write_segment_pdf(source_doc, segment.canonical_pages, category_dir / f"{stem}.pdf", segment.title)
            if write_text:
                category_dir.mkdir(parents=True, exist_ok=True)
                chunks = [by_page[page].text for page in segment.canonical_pages if page in by_page]
                header = (
                    f"TITLE: {segment.title}\n"
                    f"SEGMENT_ID: {segment.segment_id}\n"
                    f"CATEGORY: {segment.category}\n"
                    f"ORIGINAL_CANONICAL_PAGES: {_page_ranges(segment.canonical_pages)}\n\n"
                )
                (category_dir / f"{stem}.txt").write_text(header + "\n\n".join(chunks), encoding="utf-8")

        if write_deduped_pdf and source_doc is not None:
            unique_pages = [record.original_page for record in records if record.duplicate_of is None]
            _write_segment_pdf(source_doc, unique_pages, output_dir / "deduplicated.pdf", "Deduplicated corpus")
    finally:
        if source_doc is not None:
            source_doc.close()


def run_pipeline(
    source: str | Path,
    output_dir: str | Path,
    *,
    boundary_threshold: float = 5.0,
    min_text_for_text_hash: int = 80,
    config_path: str | Path | None = None,
    rescan: bool = False,
    write_pdfs: bool = True,
    write_text: bool = True,
    write_deduped_pdf: bool = False,
    segment_first: bool = False,
) -> dict[str, object]:
    source = Path(source)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    config = Config.load(config_path)

    records = scan_pdf(
        source,
        output_dir,
        min_text_for_text_hash=min_text_for_text_hash,
        rescan=rescan,
    )
    # Keep duplicate pages as structural evidence and in their source documents.
    segmentation_records = [replace(r, duplicate_of=None) for r in records] if segment_first else records
    segments, decisions = build_segments(
        segmentation_records,
        boundary_threshold=boundary_threshold,
        config=config,
    )
    stats = write_manifests(output_dir, records, segments, decisions)
    if segment_first:
        from .segment_first import build_segment_occurrences

        occurrences, _ = build_segment_occurrences(
            records, boundary_threshold=boundary_threshold, config=config,
        )
        assert [s.canonical_pages for s in segments] == [o.original_pages for o in occurrences]
        manifest_dir = output_dir / "manifests"
        (manifest_dir / "document_occurrences.json").write_text(
            json.dumps([o.to_json() for o in occurrences], indent=2), encoding="utf-8",
        )
        locations = {}
        for segment in segments:
            stem = f"{segment.category}/{segment.segment_id:04d}_{segment.slug}"
            for offset, page in enumerate(segment.canonical_pages, 1):
                locations[page] = (segment.segment_id, stem + ".pdf", offset)
        with (manifest_dir / "export_page_map.csv").open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.writer(handle)
            writer.writerow(["original_page", "segment_id", "pdf_path", "pdf_page", "canonical_page", "canonical_pdf_path", "canonical_pdf_page"])
            for record in records:
                canonical = record.duplicate_of or record.original_page
                sid, path, offset = locations[record.original_page]
                _, canonical_path, canonical_offset = locations[canonical]
                writer.writerow([record.original_page, sid, path, offset, canonical, canonical_path, canonical_offset])
        stats.update(
            segmentation_order="segment_first",
            duplicate_pages_retained_in_exports=True,
            exported_pages=sum(s.page_count for s in segments),
            duplicate_document_occurrences=sum(o.duplicate_of_segment_id is not None for o in occurrences),
        )
        (manifest_dir / "stats.json").write_text(json.dumps(stats, indent=2), encoding="utf-8")
    write_split_outputs(
        source,
        output_dir,
        records,
        segments,
        write_pdfs=write_pdfs,
        write_text=write_text,
        write_deduped_pdf=write_deduped_pdf,
    )
    return stats
