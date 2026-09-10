# pdfresearch

Local-first PDF corpus deduplication, boundary detection, splitting, privacy flagging, and provenance mapping for very large merged research PDFs.

This repository is intentionally **code-only**. Do not commit the source corpus, split outputs, health records, NDIS material, bank details, or other personal documents. The target workflow is local processing on Josh's own machine, then optional ingestion of the cleaned outputs into a local RAG system such as AnythingLLM/Open WebUI.

## What it does

`pdfresearch` performs an end-to-end pass over one large PDF and produces:

- page-level exact deduplication using normalised text, with a safer structural fallback for near-blank pages;
- a provenance map from every original page to its canonical page (duplicates are recorded, not forgotten);
- heuristic document-boundary detection using running headers, page-number resets, title-like typography, page geometry, font signatures, blank separators, and gaps created by removed duplicate runs;
- named split PDFs plus matching UTF-8 text files;
- separation of likely third-party/reference works from personal/research material;
- privacy flags by *type and page only* (matched values are never written to the report);
- CSV/JSON manifests suitable for independent review;
- a resumable page-scan cache for very large files.

The splitter is deliberately deterministic and local. It does **not** send pages to an LLM or external API.

## Install

Requires Python 3.11+.

```bash
python -m venv .venv
# Windows PowerShell
.\.venv\Scripts\Activate.ps1
# Linux/macOS
# source .venv/bin/activate

pip install -e .
```

## Run

```bash
pdfresearch run "_DEEP_RESEARCH_.pdf" --output "pdfresearch-output"
```

For a first pass that scans and builds manifests without writing hundreds of split PDFs:

```bash
pdfresearch run "_DEEP_RESEARCH_.pdf" --output "pdfresearch-output" --no-pdfs
```

Then inspect `segments.csv`, `boundary_review.csv`, and `privacy_flags.csv`. Re-run with PDFs enabled once the boundary threshold/config looks right.

To preserve source-document structure, use `--segment-first`. This splits the
original page stream and retains every page, including duplicates, in the exports.
Duplicate pages are still identified in the manifests; `document_occurrences.json`
also identifies repeated document occurrences by their page hashes.
`export_page_map.csv` maps each original page to its exported PDF and page number,
plus the exported location of its canonical duplicate match. Hash matches indicate
normalised-text/structural equivalence, not guaranteed visual identity.

```bash
pdfresearch run "INPUT.pdf" --output "pdfresearch-output" --segment-first
```

Split export preserves original page objects, including filled widgets and page
transparency groups. Cross-split page links point back to the original source PDF;
retain the source and folder layout if those links are needed. See
[full-corpus validation](docs/FULL_CORPUS_VALIDATION.md) for measured fidelity,
duplicate-definition reconciliation, and remaining interpretation limits.

Useful options:

```bash
pdfresearch run INPUT.pdf --output OUTDIR \
  --boundary-threshold 5.0 \
  --min-text-for-text-hash 80 \
  --write-text
```

The scan cache is stored under `OUTDIR/.cache/`. Re-running against the same source resumes from the completed page count unless `--rescan` is supplied.

## Output layout

```text
pdfresearch-output/
  personal/                  # likely own-authored/personal research documents
    0001_title.pdf
    0001_title.txt
  reference/                 # likely third-party/reference works
    0042_the_hobbit.pdf
    0042_the_hobbit.txt
  manifests/
    segments.csv
    segments.json
    page_map.csv
    duplicate_groups.csv
    boundary_review.csv
    privacy_flags.csv
    stats.json
  .cache/
    pages.jsonl
    source.json
```

## Important interpretation notes

### Deduplication

A duplicate page is never silently deleted from history. The first occurrence becomes the canonical page and every later occurrence is mapped to it in `page_map.csv`. This preserves provenance while keeping the research corpus compact.

For pages with substantial text, exact duplicate detection hashes aggressively normalised text. For near-blank pages, the hash also incorporates geometry, fonts, and image object fingerprints to reduce false positives.

### Splitting

Boundary detection is heuristic. Every proposed boundary gets a score and human-readable reasons in `boundary_review.csv`. The intent is to make the hard part **auditable** rather than hide it behind an LLM judgement.

Do not assume all boundaries are correct on the first run. Review low-margin boundaries, adjust `--boundary-threshold`, and rerun. The original PDF is never modified.

### Privacy

Privacy detection is a warning system, not a redactor. It records only categories such as `email`, `phone`, `ndis_context`, `bank_context`, `vin`, etc. It does not output the matched identifier. Redact source material before uploading cleaned documents to any hosted service.

## Review workflow

For multiple reviewers:

1. Run `--no-pdfs` first.
2. Commit only code/config changes, **never the private manifests or corpus**.
3. Compare `boundary_review.csv` locally.
4. Tune boundary rules/config in pull requests.
5. Once stable, generate split PDFs locally and ingest only the material you intend to analyse.

## Status

This is the first reviewable implementation. The next validation step is to run it against the 24,580-page merged corpus and compare its measured duplicate count and split boundaries with the independent corpus scan already performed elsewhere. Any mismatch should be treated as useful evidence, not forced to match a preconceived number.
