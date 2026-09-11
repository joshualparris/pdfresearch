import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
import psutil

def get_subset_pdf(source_path: Path, temp_path: Path, ranges: list[tuple[int, int]]):
    import pymupdf
    doc = pymupdf.open(source_path)
    doc2 = pymupdf.open()
    for start_page, num_pages in ranges:
        end_page = min(start_page + num_pages - 1, doc.page_count - 1)
        doc2.insert_pdf(doc, from_page=start_page, to_page=end_page)
    doc2.save(temp_path)
    doc2.close()
    doc.close()

def run_pymupdf4llm(pdf_path: Path):
    import pymupdf
    import pymupdf4llm
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

def get_system_memory_info():
    vm = psutil.virtual_memory()
    swap = psutil.swap_memory()
    return {
        "ram_used_gb": round((vm.total - vm.available) / (1024**3), 2),
        "ram_total_gb": round(vm.total / (1024**3), 2),
        "swap_used_gb": round(swap.used / (1024**3), 2),
        "swap_total_gb": round(swap.total / (1024**3), 2),
    }

def benchmark_library_subprocess(name: str, pdf_path: Path):
    print(f"\n--- Benchmarking {name} ---")
    sys_mem_before = get_system_memory_info()
    print(f"System memory BEFORE: {sys_mem_before}")
    
    cmd = ["/usr/bin/time", "-v", sys.executable, __file__, "--worker", name, "--pdf", str(pdf_path)]
    
    start_time = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True)
    end_time = time.time()
    
    sys_mem_after = get_system_memory_info()
    print(f"System memory AFTER: {sys_mem_after}")
    
    success = (result.returncode == 0)
    error = None
    if not success:
        error = f"Process exited with code {result.returncode}. Stderr:\n{result.stderr}"
    
    peak_memory_mb = 0.0
    mem_match = re.search(r"Maximum resident set size \(kbytes\):\s+(\d+)", result.stderr)
    if mem_match:
        peak_memory_mb = round(int(mem_match.group(1)) / 1024, 2)
        
    result_length = 0
    if success:
        try:
            # The worker prints a JSON dictionary to stdout as its last output line
            # It may have printed other stuff, so grab the last line
            lines = result.stdout.strip().splitlines()
            if lines:
                worker_out = json.loads(lines[-1])
                result_length = worker_out.get("length", 0)
        except Exception as e:
            error = f"Failed to parse worker output: {e}"
            success = False
            
    return {
        "name": name,
        "success": success,
        "runtime_seconds": round(end_time - start_time, 2),
        "peak_memory_mb": peak_memory_mb,
        "sys_mem_before_gb": sys_mem_before,
        "sys_mem_after_gb": sys_mem_after,
        "error": error,
        "result_length": result_length,
    }

def worker_main(name: str, pdf_path: Path):
    try:
        if name == "PyMuPDF4LLM":
            res = run_pymupdf4llm(pdf_path)
        elif name == "Docling":
            res = run_docling(pdf_path)
        elif name == "Unstructured":
            res = run_unstructured(pdf_path)
        else:
            raise ValueError(f"Unknown library: {name}")
            
        with open(f"output_{name}.txt", "w", encoding="utf-8") as f:
            f.write(res.get("text", ""))
            
        # Output result length to stdout for the parent process
        print(json.dumps({"length": res.get("length", 0)}))
    except Exception as e:
        print(f"Worker failed: {e}", file=sys.stderr)
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--worker", type=str, help="Run as worker for specific library")
    parser.add_argument("--pdf", type=str, help="PDF path for worker")
    args = parser.parse_args()
    
    if args.worker:
        worker_main(args.worker, Path(args.pdf))
        return

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
    results.append(benchmark_library_subprocess("PyMuPDF4LLM", temp_pdf))
    results.append(benchmark_library_subprocess("Docling", temp_pdf))
    results.append(benchmark_library_subprocess("Unstructured", temp_pdf))
    
    print("\n--- Benchmark Results ---")
    print(json.dumps(results, indent=2))
    
    if temp_pdf.exists():
        temp_pdf.unlink()

if __name__ == "__main__":
    main()
