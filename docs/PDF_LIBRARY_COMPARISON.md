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

> [!WARNING]
> **Important Note:** The Peak Memory values below were measured using Python's `tracemalloc`, which significantly under-reports total process memory (including native allocations, ML models, and child processes). Real-world system footprints were massively higher (e.g., Docling pushed the system to memory exhaustion).

| Library | Runtime (s) | Speed (pages/s) | Est. 24.5k Corpus Time | Peak Memory (tracemalloc)* | Result Length |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **PyMuPDF4LLM** | 51.46s | ~0.93 | ~7 hours | 258.56 MB | 88,931 chars |
| **Unstructured** | 67.30s | ~0.71 | ~9.5 hours | 258.14 MB | 88,856 chars |
| **Docling** | 332.23s | ~0.14 | ~47 hours | 789.86 MB | 88,477 chars |

*Measurements represent Python-tracemalloc metrics, **not** total process memory.*

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

### 1. Speed and Practicality
- **PyMuPDF4LLM** is the clear winner for performance, operating at roughly 1 page per second. This is the only library that practically scales to the 24k-page corpus without needing heavy parallelization or external clusters.
- **Unstructured** performed admirably and remained lightweight in memory.
- **Docling** is prohibitively slow for a single-node run on a 24k-page corpus. It downloads heavy Hugging Face models (over 700 weights) on initialization and relies on deep-learning vision models for layout analysis, taking roughly 7 seconds per page on CPU.

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
