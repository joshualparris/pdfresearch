# Independent second-pass review

Date: 11 September 2026

This review deliberately approached the splitter separately from the implementation already on `main`. The goal is not to force agreement with the earlier corpus report; it is to find failure modes before the 24,580-page source is trusted.

## Headline finding

The architectural concern already identified in `REVIEW.md` is real and reproducible: **global page deduplication before segmentation can damage document structure**.

Two synthetic regressions now demonstrate this:

1. A legitimate repeated page inside one source document disappears from the source occurrence before boundary inference/output.
2. If an entire source document is repeated later in the merge, removing its pages first means the later source occurrence — and its boundary — no longer exists for the segmenter to inspect.

The new `pdfresearch.segment_first` audit path does not replace the production pipeline yet. It provides an independent comparison:

1. page duplicates are detected but retained;
2. the original page stream is segmented;
3. exact duplicate *document occurrences* are fingerprinted after segmentation.

Run it locally with:

```bash
python tools/segment_first_audit.py "_DEEP_RESEARCH_.pdf" --output pdfresearch-output
```

It writes only structural metadata to `pdfresearch-output/manifests/segment_first_audit.json`; it does not write extracted page text.

## Independent sample observations

Before reviewing the current `main` implementation, a separate prototype was exercised against the files available in the review environment.

### Standalone-report regression set

Eight unrelated standalone PDFs (3 to 74 pages each) were used as negative controls for false splitting. After tuning, the independent prototype produced only the expected start boundary for each file. The useful lessons were:

- normal chapter/bookmark entries must not automatically be treated as source-document boundaries;
- a transient landscape/table page must not, by itself, create a source boundary when the document returns to portrait;
- running headers, printed page resets and title cues are more useful when combined than when trusted individually.

These observations are **not** claims that the current `main` implementation has those exact bugs. They are regression cases worth keeping in mind as the scorer evolves.

### 1,413-page merged sample

A separate 1,413-page merged PDF available in the review environment was also used as a development sample. The independent prototype proposed 50 source segments and successfully wrote 50 PDFs. First-page renders from an early, middle and final split were manually inspected and were plausible source starts.

Important limitations:

- this is **not** the 24,580-page target corpus;
- the sample contained no exact duplicate pages under the prototype's text hash, so it cannot validate the reported 54% duplicate rate;
- the sample had a substantial PDF outline, so it is not representative of the target corpus if the target truly has no useful outline/bookmarks;
- 50 plausible outputs is not a precision/recall measurement. A labelled boundary set is still required.

## What should happen next

The safest next validation is an A/B run on the real corpus with PDFs disabled:

```bash
pdfresearch run "_DEEP_RESEARCH_.pdf" --output pdfresearch-output --no-pdfs
python tools/segment_first_audit.py "_DEEP_RESEARCH_.pdf" --output pdfresearch-output
```

Then compare the two segmentation orders around:

- known repeated whole documents;
- known repeated one-page artefacts;
- pages immediately before and after long duplicate runs;
- a stratified sample of accepted and near-threshold boundaries.

Do not choose whichever method lands closest to the previously reported `13,267` duplicate pages or `~226` own-authored documents. Resolve disagreements against the source pages.

## Public-repository rule

This repository is public. No source PDF, extracted personal text, real manifest, screenshot, identifier, health record, family material, NDIS material, bank detail or tenancy record was committed as part of this review. Synthetic tests only.
