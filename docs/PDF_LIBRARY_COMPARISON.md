# PDF Extraction Library Comparison

This report evaluates three PDF extraction libraries (`Docling`, `PyMuPDF4LLM`, and `Unstructured`) for their suitability in extracting enhanced document-boundary signals, handling messy/scanned PDFs, and operating practically at a 24,580-page scale.

## Methodology

A custom script (`tools/compare_libraries.py`) extracted 48 representative scattered pages from the full `_DEEP RESEARCH .pdf` corpus. These pages were specifically selected to cover a wide range of edge cases, including:
- Known real boundaries and missed boundaries
- Continuations and chapter headings
- Forms and widgets
- Image-only and near-blank pages
- Visually distinct duplicate pages (same-text but visually different)
- Layout-heavy pages (tables and images)

The libraries were benchmarked on their raw performance (Runtime and Peak Memory).

## Benchmark Results

| Library | Runtime (s) | Speed (pages/s) | Est. 24.5k Corpus Time | Peak Combined RSS | Result Length |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **PyMuPDF4LLM** | 56.42s | ~0.85 | ~8 hours | 966.56 MB | 88,931 chars |
| **Unstructured** | 34.84s | ~1.38 | ~5 hours | 576.53 MB | 88,856 chars |
| **Docling** | 389.46s | ~0.12 | ~55 hours | 3,415.57 MB | 88,477 chars |

*Measurements represent true Peak RSS over the entire subprocess tree. All libraries successfully completed within the 12GB RAM / 8GB Swap systemd limit.*

### Safe Execution Strategy

To accurately measure total process memory footprint (Peak RSS) and prevent future Out-Of-Memory (OOM) situations from crashing critical services, future benchmarks must be run in complete isolation with strict memory constraints. 

Use the following helper command to run the updated benchmarking script inside a constrained `systemd` scope:

```bash
systemd-run --user --scope \
  -p MemoryMax=12G \
  -p MemorySwapMax=8G \
  bash -lc 'cd /home/josh/dev/pdfresearch-validation && source .venv/bin/activate && python tools/compare_libraries.py'
```


## Evaluation

### 1. Speed, Memory, and Practicality
- **Unstructured** is remarkably fast in isolated execution (completing in 34.8s) and remained the most lightweight library at ~576 MB Peak RSS. It easily scales to the full 24k-page corpus.
- **PyMuPDF4LLM** operates reliably at under 1 page per second. While its real memory footprint (~966 MB) was roughly four times higher than the old flawed `tracemalloc` measurement, it remains highly practical for local extraction without hitting resource limits.
- **Docling** is prohibitively slow for a single-node run on a 24k-page corpus and extremely memory-hungry. It consumed over 3.4 GB of Peak RSS (plus roughly 2 GB of Swap) just to process 48 pages. It relies on downloading heavy Hugging Face models (over 700 weights) on initialization and running deep-learning vision models for layout analysis, taking over 8 seconds per page on CPU.

### 2. Distinguishing Visually Different Duplicates
The text outputs across all three libraries were heavily comparable (all returning ~88-89k characters). 
When dealing with pages that share the exact same structural text but differ visually (e.g. scans where `render=False`), Docling and Unstructured attempt to rely on OCR (RapidOCR and Tesseract respectively). However, since the underlying visual differences are often subtle pixel-level variations rather than new text, purely relying on the extracted text output does **not** solve the safety failure where visually distinct pages are deduplicated.
To correctly distinguish them, we need true render/geometry hash comparisons, which PyMuPDF provides natively.

### 3. Boundary Signals
- **PyMuPDF4LLM** provides excellent markdown structure out-of-the-box and easily identifies headers, which provides a strong signal for document boundaries. 
- **Docling** excels at visual layout analysis, capturing complex tables and multicolumn layouts perfectly, but its runtime cost outweighs these benefits for boundary detection alone.
- **Unstructured** parses elements well but requires more complex integration to cleanly separate headers from standard paragraphs in a markdown format compared to PyMuPDF4LLM.

## Recommendations

1. **Retain PyMuPDF as the core engine:** We should continue to use PyMuPDF for geometric/render comparisons to ensure visually distinct pages are never falsely deduplicated. 
2. **Integrate PyMuPDF4LLM for Boundary Detection:** PyMuPDF4LLM is the most practical choice for providing Markdown representations to aid boundary detection. It is fast enough to run across the entire corpus in under 8 hours locally and provides clean structural signals (e.g., `# Headings`).
3. **Avoid Docling for now:** While Docling produces phenomenal results on complex layouts, it is simply too heavy for our current 24k-page corpus without a dedicated GPU/cluster setup.

**Next Steps:** We should use the 48-page subset generated in this spike to create new deterministic synthetic fixtures for Antigravity, particularly for the visually distinct edge cases.
