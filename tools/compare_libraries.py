import time
import tracemalloc
import pymupdf
import pymupdf4llm
from pathlib import Path
import json

def get_subset_pdf(source_path: Path, temp_path: Path, ranges: list[tuple[int, int]]):
    doc = pymupdf.open(source_path)
    doc2 = pymupdf.open()
    for start_page, num_pages in ranges:
        end_page = min(start_page + num_pages - 1, doc.page_count - 1)
        doc2.insert_pdf(doc, from_page=start_page, to_page=end_page)
    doc2.save(temp_path)
    doc2.close()
    doc.close()

def run_pymupdf4llm(pdf_path: Path):
    doc = pymupdf.open(pdf_path)
    md_text = pymupdf4llm.to_markdown(doc)
    doc.close()
    return {"length": len(md_text), "preview": md_text[:500], "text": md_text}

def run_docling(pdf_path: Path):
    from docling.document_converter import DocumentConverter
    converter = DocumentConverter()
    result = converter.convert(str(pdf_path))
    md_text = result.document.export_to_markdown()
    return {"length": len(md_text), "preview": md_text[:500], "text": md_text}

def run_unstructured(pdf_path: Path):
    from unstructured.partition.pdf import partition_pdf
    elements = partition_pdf(str(pdf_path))
    text = "\n\n".join([str(e) for e in elements])
    return {"length": len(text), "preview": text[:500], "text": text}

def benchmark_library(name: str, func, pdf_path: Path):
    print(f"Benchmarking {name}...")
    tracemalloc.start()
    start_time = time.time()
    try:
        res = func(pdf_path)
        success = True
        error = None
        with open(f"output_{name}.txt", "w", encoding="utf-8") as f:
            f.write(res.get("text", ""))
    except Exception as e:
        success = False
        res = {}
        error = str(e)
    end_time = time.time()
    _, peak = tracemalloc.get_traced_memory()
    tracemalloc.stop()
    
    return {
        "name": name,
        "success": success,
        "runtime_seconds": round(end_time - start_time, 2),
        "peak_memory_mb": round(peak / 1024 / 1024, 2),
        "error": error,
        "result_length": res.get("length", 0),
    }

def main():
    source_pdf = Path("/home/josh/dev/pdfresearch/_DEEP RESEARCH .pdf")
    temp_pdf = Path("temp_comparison.pdf")
    
    if not source_pdf.exists():
        print(f"Source PDF not found at {source_pdf}")
        return
        
    print(f"Extracting scattered pages from {source_pdf}...")
    ranges = [
        (10, 6),
        (100, 6),
        (6088, 6),   # visually distinct
        (6192, 6),   # visually distinct
        (11645, 6),  # visually distinct
        (15000, 6),
        (24000, 6),
        (24500, 6)
    ]
    get_subset_pdf(source_path=source_pdf, temp_path=temp_pdf, ranges=ranges)
    
    results = []
    results.append(benchmark_library("PyMuPDF4LLM", run_pymupdf4llm, temp_pdf))
    results.append(benchmark_library("Docling", run_docling, temp_pdf))
    results.append(benchmark_library("Unstructured", run_unstructured, temp_pdf))
    
    print("\n--- Benchmark Results ---")
    print(json.dumps(results, indent=2))
    
    if temp_pdf.exists():
        temp_pdf.unlink()

if __name__ == "__main__":
    main()
