# Review guide

This repository is intentionally at the **first independently reviewable implementation** stage. The code is not allowed to assume that the previously reported 24,580 total pages / 13,267 duplicate pages / ~226 source documents are correct. Those numbers are validation targets from an independent scan, not constants.

## What reviewers should attack first

### 1. Duplicate safety

`scan_pdf()` treats the first page with a given hash as canonical and maps later copies to it. For text-rich pages the hash is based on NFKC/case/whitespace-normalised text. For near-blank pages it additionally includes geometry, font signature and image fingerprints.

Please look for false-positive cases such as:

- boilerplate pages with identical text but meaningfully different images;
- repeated blank separators that should remain as structural evidence;
- forms/templates whose text is identical but handwriting/annotations differ;
- OCR layers that are identical while the underlying scan differs.

If the real corpus contains these, the hash should incorporate a visual/object fingerprint for those page classes before production use.

### 2. Boundary calibration

The split scorer is deliberately heuristic and transparent. Review `src/pdfresearch/signals.py` rather than trusting a black-box score.

High-value checks:

- report page-number resets;
- running-header changes;
- duplicate-run gaps after a repeated source document has been removed;
- cover/title typography;
- page-size changes;
- false splits at chapter headings inside books/reports;
- missed splits where adjacent reports use the same template/font set.

Every candidate is exported to `boundary_review.csv`. The intended workflow is calibration + human override, not one-shot automation.

### 3. Global dedupe versus segmentation order

The current design deduplicates first, then segments canonical pages in original order. This is efficient for a corpus made by repeatedly merging whole documents, but there is a subtle risk: a legitimate repeated page inside a document can disappear before segmentation.

A reviewer may prefer a two-stage design:

1. detect duplicate groups but retain all pages for boundary inference;
2. segment the original stream;
3. dedupe duplicate *documents* and duplicate pages within the chosen canonical representation.

This is probably the most important architectural question for the 24,580-page corpus.

### 4. Privacy detection

The privacy detector is a **warning system only**. It intentionally writes categories and page numbers, never matched values. Review regexes for both false positives and missed Australian identifiers.

Do not add real personal identifiers to tests or issues. Use synthetic data only.

### 5. Reference classification

Built-in rules identify obvious third-party/reference families (Tolkien, Psalms/Constable, Goodfellow/Bengio/Courville, D&D SRD, LPIC/Linux+, academic/legal publications). These are convenience heuristics, not provenance proof.

Check whether a personal report *discussing* one of those works gets misclassified as the work itself. The config file can override classifications while a stronger classifier is developed.

### 6. Performance

Target scale is roughly 25k pages / hundreds of MB. The scan is resumable, but please profile:

- `page.get_text("dict")` throughput;
- image extraction on near-blank pages;
- JSONL cache size and load time;
- PDF rewriting time with `garbage=3, deflate=True`;
- memory footprint when all `PageRecord.text` strings are resident.

A production optimisation may split the pipeline into a compact metadata pass and on-demand text materialisation.

## Suggested first corpus run

Run manifests only first:

```bash
pdfresearch run "_DEEP_RESEARCH_.pdf" --output "pdfresearch-output" --no-pdfs
```

Then compare:

- total pages;
- unique page count;
- duplicate groups and their run lengths;
- segment count;
- the 100 boundaries closest to threshold;
- obvious known report starts/ends;
- reference/personal classification.

Do **not** tune the algorithm merely to hit the independent scan's reported counts. Investigate disagreements page-by-page and record which method is right.

## Data handling

The GitHub repository is public. Never commit source PDFs, extracted text, manifests from the real corpus, screenshots, logs containing personal text, or example identifiers. If evidence is needed for a bug report, construct a synthetic PDF reproducer.
