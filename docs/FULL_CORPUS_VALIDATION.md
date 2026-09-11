# Full-corpus validation lane

This is a local run report, not a labelled ground-truth dataset. The original
corpus, titles, source text, outputs, screenshots, configuration and per-page
manifests remain outside this branch. Production boundary weights were not changed.

## Frozen structural results

The current configuration produced 24,580 source pages, 13,361 duplicate page
matches, 11,219 distinct page hashes, and 548 proposed document occurrences:
493 classified personal/research and 55 reference. It marks 183 occurrences as
repeated, leaving 365 representative occurrences. All 24,580 pages are retained
in the 548 PDF/text pairs. The preceding configuration produced 551 occurrences
and 178 repeats; combining 548 with 178 mixes two different snapshots.

These are algorithm/configuration results. Neither the counts, inferred boundaries
nor default-to-personal classifications constitute verified authorship or truth.
The local structural audit contains page ranges, scores/reasons, duplicate-group
sizes, fingerprints and classification reasons without including titles or text.
Local review overrides are not shipped as generally applicable boundary rules.

## Duplicate definitions reconciled

Claude's supplied detector was run unmodified against the same source using the
same PyMuPDF installation. It reproduced **13,167** duplicates and excluded 297
pages with fewer than 30 characters after its whitespace/lowercase normalization.
A fresh per-page map permits direct comparison:

- The current detector adds **194** duplicate-page classifications; Claude adds none.
- **186** extra matches are on pages excluded by Claude's 30-character cutoff.
  The current detector instead hashes their text, geometry, fonts and image fingerprints.
- **8** extra matches result from removal of U+200B zero-width spaces. NFKC or
  case folding alone does not explain these eight cases.
- **16** pages are duplicates in both runs but point to different first occurrences
  because the normalized groups merge. **13,151** duplicate pairs agree exactly.

The historical **13,267** can also be reproduced by exact-matching the current
extracted text while excluding empty strings. Including the empty-string bucket
produces 11,143 distinct texts and 13,437 duplicate occurrences. There are 171
empty-text pages, so excluding their 170 repeats gives 13,267. This explains the
historical report's arithmetic gap, but it does **not** establish which extraction
or normalization code that historical scan actually used; its raw map is missing.

Sampling 258 current duplicate pairs found 39 render differences at 72 dpi,
including 14 near-blank/vector cases and 25 text-rich layout/geometry cases.
There were no widget-value or annotation-signature differences in that sample.
This is not a random precision estimate. Text/structural hash equality must not
be presented as visual identity or used as sufficient evidence to delete pages.
Neither implementation strips footer dates for deduplication; changes to visible
numbers/dates remain meaningful differences under their text hashes.

## Export failures and repair

The original insert-based export exhibited two distinct failures:

1. Some merged pages retained widget annotations and visible filled appearances,
   although the source catalog had lost its AcroForm registration. `insert_pdf`
   dropped those widgets. Comparing text alone did not detect all affected pages.
2. Page insertion omitted a page's `/Group` transparency dictionary, changing its
   rendering while preserving its text and embedded font streams.

The exporter now selects pages from a fresh copy of the original PDF. This keeps
page dictionaries, widgets, field names/values, annotations and graphics objects
rather than flattening or rebuilding their visible content. It uses an in-memory
snapshot when the caller has unsaved changes.

Internal links to retained pages stay internal. Links to omitted source pages
become relative GoToR links back to the original PDF, preserving the original
PDF destination view/coordinates. Existing relative file links are rebased for
the split file's location. Such navigation depends on retaining the source and
relative directory layout; this is not a self-contained replacement for the
source PDF. The convenience API may report zero coordinates for remote links,
so the audit compares the underlying destination array as well.

The full audit also caught `select()` deleting 1,268 named-link annotations. Their
original objects are now restored after selection. They retain the source's
behaviour; this does not repair missing destinations. URI actions misreported as
file links, encoded platform-specific paths, shared indirect action dictionaries,
and indirect URI/file strings are covered by additional regressions.

Synthetic regressions cover orphan forms, editable registered forms, field values,
annotations, links inside/outside the split, relative file links, images, vector
transparency, rotation/crop boxes, ordinary text and unsaved source edits.

The local two-strategy comparison covered 40 source pages, including all 25 widget
pages and the corpus's annotation-bearing page. Insertion failed 25 widget checks,
15 text checks, 25 render checks and 3 transparency-group-presence checks. The
object-preserving selection strategy passed those comparisons. The final full-page
audit passed on **24,580 pages / 548 PDFs**, retaining **1,386 widgets**, the source's
non-link annotation, and **17,456 links**. All **646 sampled 72-dpi renders** matched.
After link repairs, all 284 pages in the 17 affected documents were rechecked;
their results replace those documents' earlier measurements. No mismatches remain
within the stated audit scope. The source file's size/mtime and SHA-256 identity
were recorded, and all 548 text sidecars matched the extraction cache.

This was measured with PyMuPDF 1.28.2. Rebuilding all 548 PDFs using fresh source
copies took about 944 seconds before focused link repairs. Correctness currently
takes priority over optimizing repeated source loading. Fifteen synthetic tests
and the configured Ruff checks pass on the validation branch.

## Reproducing local audits

```bash
pdfresearch run INPUT.pdf --output pdfresearch-output --segment-first --config LOCAL_CONFIG.toml
python tools/structural_audit.py pdfresearch-output
python tools/audit_export_fidelity.py INPUT.pdf pdfresearch-output --render-pages LOCAL_PAGE_LIST.json
```

The fidelity audit compares every exported page's text hash, widget count and
value/name hash, annotation types/signature, link count/destination signature,
geometry/rotation and transparency-group presence. Requested renders are compared
at 72 dpi. It writes hashes and structural metadata, never extracted text or
matched identifiers. Equality at one renderer/resolution is bounded evidence,
not a guarantee of every PDF viewer's interactive behaviour.

Text sidecars extract existing text layers; they do not OCR image-only pages.
Privacy/context flags are review aids, not redaction or clearance to publish.
Selecting pages is not a sanitization/redaction operation either.

## Cases for the synthetic evaluation lane

- Orphan widget annotations with visible text but no catalog AcroForm registration.
- Identical page text and font streams with a required transparency-group dictionary.
- Equal normalized text but changed layout, page geometry or graphics.
- Near-blank pages with different vector paths and no image objects: current hashes
  can collide despite visible differences. Add drawings/signatures rendered as paths.
- Image-only pages with differing image placement, transforms or masks.
- U+200B differences that merge groups and change canonical-page identities.
- Blank exclusion versus a retained blank-text bucket in aggregate accounting.
- Cross-segment links with non-default PDF destination views and relative file links.
- Matching-text forms with changed widget values, handwritten marks or signatures.
- Footer-date changes that should remain distinguishable.
- Repeated pages within a document and repeated whole documents in the original stream.

The boundary scorer should be evaluated against labelled examples before tuning;
no claim of improved precision/recall follows merely from fewer output segments.
