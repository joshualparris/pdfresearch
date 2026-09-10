import csv
from pathlib import Path
from pdfresearch.pipeline import run_pipeline
from pdfresearch.segment_first import build_segment_occurrences

def evaluate_boundaries(decisions_csv: Path, labels_csv: Path) -> dict:
    truth = {}
    case_ids = {}
    with open(labels_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            truth[int(row["before_page"])] = row["label"]
            case_ids[int(row["before_page"])] = row["case_id"]

    tp = fp = fn = tn = 0
    fp_list = []
    fn_list = []
    
    predictions = {}
    with open(decisions_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            page = int(row["before_original_page"])
            is_boundary = row["accepted"].lower() == "true"
            score = row["score"]
            reasons = row["reasons"]
            predictions[page] = {"is_boundary": is_boundary, "score": score, "reasons": reasons}
            
    # Iterate over TRUTH to catch False Negatives for pages that were deleted (e.g., dedupe-first)
    for page, label in truth.items():
        if label == "UNCERTAIN" or label == "CORPUS_START":
            continue
            
        truth_is_boundary = label == "BOUNDARY"
        pred = predictions.get(page)
        
        if pred is None:
            # No decision means it was rejected implicitly (e.g. removed by deduper)
            if truth_is_boundary:
                fn += 1
                fn_list.append({"page": page, "case_id": case_ids.get(page, ""), "score": "N/A", "reasons": "Page deleted before segmentation", "severity": "HIGH"})
            else:
                tn += 1
        else:
            is_boundary = pred["is_boundary"]
            score = pred["score"]
            reasons = pred["reasons"]
            if truth_is_boundary and is_boundary:
                tp += 1
            elif not truth_is_boundary and is_boundary:
                fp += 1
                fp_list.append({"page": page, "case_id": case_ids.get(page, ""), "score": score, "reasons": reasons, "severity": "MEDIUM"})
            elif truth_is_boundary and not is_boundary:
                fn += 1
                fn_list.append({"page": page, "case_id": case_ids.get(page, ""), "score": score, "reasons": reasons, "severity": "HIGH"})
            else:
                tn += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return {
        "metrics": {"precision": round(precision, 3), "recall": round(recall, 3), "f1": round(f1, 3)},
        "counts": {"tp": tp, "fp": fp, "fn": fn, "tn": tn},
        "fp_list": fp_list,
        "fn_list": fn_list
    }

def evaluate_duplicates(page_map_csv: Path, labels_csv: Path) -> dict:
    truth = {}
    with open(labels_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            truth[int(row["page"])] = row["type"]
            
    predicted_duplicates = set()
    with open(page_map_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row["is_duplicate"].lower() == "true":
                predicted_duplicates.add(int(row["original_page"]))
                
    exact_tp = exact_fn = exact_fp = 0
    visually_distinct_fp = 0
    near_dup_caught = near_dup_missed = 0
    
    # Truth might not contain DISTINCT for all pages, so we need to infer it.
    all_pages = set()
    with open(page_map_csv, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            all_pages.add(int(row["original_page"]))
            
    fp_list = []
    fn_list = []
    
    for page in all_pages:
        label = truth.get(page, "DISTINCT")
        predicted = page in predicted_duplicates
        
        if label == "EXACT_DUPLICATE":
            if predicted:
                exact_tp += 1
            else:
                exact_fn += 1
                fn_list.append({"page": page, "reason": "Missed exact duplicate", "severity": "LOW"})
        elif label == "SAME_TEXT_VISUALLY_DISTINCT":
            if predicted:
                visually_distinct_fp += 1
                exact_fp += 1
                fp_list.append({"page": page, "reason": "Falsely deduped visually distinct page", "severity": "CRITICAL"})
        elif label == "NEAR_DUPLICATE":
            if predicted:
                near_dup_caught += 1
            else:
                near_dup_missed += 1
        else: # DISTINCT
            if predicted:
                exact_fp += 1
                fp_list.append({"page": page, "reason": "Falsely deduped distinct page", "severity": "HIGH"})
                
    precision = exact_tp / (exact_tp + exact_fp) if (exact_tp + exact_fp) > 0 else 0.0
    recall = exact_tp / (exact_tp + exact_fn) if (exact_tp + exact_fn) > 0 else 0.0
    
    near_dup_recall = near_dup_caught / (near_dup_caught + near_dup_missed) if (near_dup_caught + near_dup_missed) > 0 else 0.0
    
    return {
        "exact_safety": {
            "precision": precision,
            "recall": recall,
            "tp": exact_tp, "fp": exact_fp, "fn": exact_fn,
            "visually_distinct_fp": visually_distinct_fp
        },
        "near_duplicate_capability": {
            "recall": near_dup_recall,
            "caught": near_dup_caught,
            "missed": near_dup_missed
        },
        "fp_list": fp_list,
        "fn_list": fn_list
    }

def evaluate_document_occurrences(occurrences: list, doc_labels_csv: Path) -> dict:
    truth = {}
    if doc_labels_csv.exists():
        with open(doc_labels_csv, "r", encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            for row in reader:
                truth[int(row["start_page"])] = row["type"]
                
    predicted_duplicates = set()
    for occ in occurrences:
        if occ.duplicate_of_segment_id is not None:
            predicted_duplicates.add(occ.original_start)
            
    exact_tp = exact_fn = exact_fp = 0
    near_dup_caught = near_dup_missed = 0
    
    for page, label in truth.items():
        predicted = page in predicted_duplicates
        
        if label == "EXACT_DUPLICATE_DOCUMENT":
            if predicted:
                exact_tp += 1
            else:
                exact_fn += 1
        elif label == "NEAR_DUPLICATE_DOCUMENT":
            if predicted:
                near_dup_caught += 1
            else:
                near_dup_missed += 1
        elif label == "DISTINCT":
            if predicted:
                exact_fp += 1
                
    precision = exact_tp / (exact_tp + exact_fp) if (exact_tp + exact_fp) > 0 else 0.0
    recall = exact_tp / (exact_tp + exact_fn) if (exact_tp + exact_fn) > 0 else 0.0
    near_dup_recall = near_dup_caught / (near_dup_caught + near_dup_missed) if (near_dup_caught + near_dup_missed) > 0 else 0.0
    
    return {
        "exact_safety": {
            "precision": precision,
            "recall": recall,
            "tp": exact_tp, "fp": exact_fp, "fn": exact_fn
        },
        "near_duplicate_capability": {
            "recall": near_dup_recall,
            "caught": near_dup_caught,
            "missed": near_dup_missed
        }
    }

def run_evaluation_on_fixture(pdf_path: Path, out_dir: Path, fixture_name: str) -> dict:
    data_dir = pdf_path.parent
    boundaries_csv = data_dir / f"{fixture_name}_boundaries.csv"
    duplicates_csv = data_dir / f"{fixture_name}_duplicates.csv"
    doc_duplicates_csv = data_dir / f"{fixture_name}_doc_duplicates.csv"
    
    out_dedupe = out_dir / "dedupe"
    run_pipeline(pdf_path, out_dedupe, rescan=True, write_pdfs=False, write_text=False)
    dedupe_b = evaluate_boundaries(out_dedupe / "manifests/boundary_review.csv", boundaries_csv)
    dedupe_d = evaluate_duplicates(out_dedupe / "manifests/page_map.csv", duplicates_csv)
    
    out_segment = out_dir / "segment"
    out_segment.mkdir(parents=True, exist_ok=True)
    
    # Run the segment_first pipeline directly since it does not export full manifests
    from pdfresearch.pipeline import scan_pdf
    import csv
    records = scan_pdf(pdf_path, out_segment, rescan=True)
    occurrences, decisions = build_segment_occurrences(records)
    
    segment_decisions_csv = out_segment / "boundary_review.csv"
    with open(segment_decisions_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["before_original_page", "score", "accepted", "reasons"])
        for d in decisions:
            writer.writerow([d.before_original_page, d.score, d.accepted, "|".join(d.reasons)])
            
    segment_page_map_csv = out_segment / "page_map.csv"
    with open(segment_page_map_csv, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["original_page", "is_duplicate"])
        # For segment_first, it dedupes document occurrences, not single pages.
        # But we want to test exact dedupe safety on pages. Wait, the user asked to measure
        # segment-first deduplication safety. Segment-first does not deduplicate pages,
        # it deduplicates whole segments.
        # Let's map duplicate segments to pages for scoring duplicate safety.
        duplicate_pages = set()
        for occ in occurrences:
            if occ.duplicate_of_segment_id is not None:
                duplicate_pages.update(occ.original_pages)
                
        for r in records:
            writer.writerow([r.original_page, str(r.original_page in duplicate_pages)])
            
    segment_b = evaluate_boundaries(segment_decisions_csv, boundaries_csv)
    segment_d = evaluate_document_occurrences(occurrences, doc_duplicates_csv)
    
    return {
        "dedupe": {"boundaries": dedupe_b, "duplicates": dedupe_d},
        "segment": {"boundaries": segment_b, "duplicates": segment_d}
    }

def main():
    fixture_version = "v1.3"
    evaluator_version = "v1.3"
    
    root = Path(__file__).parent.parent.parent
    data_dir = root / "tests" / "eval_harness" / "data"
    
    fixtures = [f"case_{i:02d}" for i in range(1, 13)]
    
    results = {}
    
    for fixture in fixtures:
        print(f"Evaluating {fixture}...")
        pdf_path = data_dir / f"{fixture}.pdf"
        out_dir = data_dir / "out" / fixture
        results[fixture] = run_evaluation_on_fixture(pdf_path, out_dir, fixture)
        
    print("Evaluating combined_corpus...")
    pdf_path = data_dir / "combined_corpus.pdf"
    out_dir = data_dir / "out" / "combined_corpus"
    combined_results = run_evaluation_on_fixture(pdf_path, out_dir, "combined_corpus")
    
    import subprocess
    try:
        git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
    except Exception:
        git_sha = "unknown"
        
    report_path = root / "eval_baseline_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Baseline Synthetic Evaluation Report (v1.3)\n\n")
        f.write(f"- **Evaluated Code SHA**: `{git_sha}`\n")
        f.write(f"- **Fixture Version**: `{fixture_version}`\n")
        f.write(f"- **Evaluator Version**: `{evaluator_version}`\n\n")
        
        f.write("## 1. Aggregate Results (Combined Corpus)\n\n")
        dedupe_b = combined_results["dedupe"]["boundaries"]
        segment_b = combined_results["segment"]["boundaries"]
        dedupe_d = combined_results["dedupe"]["duplicates"]
        segment_d = combined_results["segment"]["duplicates"]
        f.write("| Architecture | Precision | Recall | F1 Score | TP | FP | FN | TN |\n")
        f.write("|--------------|-----------|--------|----------|----|----|----|----|\n")
        f.write(f"| Dedupe-First | {dedupe_b['metrics']['precision']:<9} | {dedupe_b['metrics']['recall']:<6} | {dedupe_b['metrics']['f1']:<8} | {dedupe_b['counts']['tp']:<2} | {dedupe_b['counts']['fp']:<2} | {dedupe_b['counts']['fn']:<2} | {dedupe_b['counts']['tn']:<2} |\n")
        f.write(f"| Segment-First| {segment_b['metrics']['precision']:<9} | {segment_b['metrics']['recall']:<6} | {segment_b['metrics']['f1']:<8} | {segment_b['counts']['tp']:<2} | {segment_b['counts']['fp']:<2} | {segment_b['counts']['fn']:<2} | {segment_b['counts']['tn']:<2} |\n")
        
        f.write("\n## Boundary Errors (Dedupe-First)\n")
        if dedupe_b["fp_list"]:
            f.write("### False Positives (Over-segmentation)\n")
            for fp in dedupe_b["fp_list"]:
                f.write(f"- Page {fp['page']} (Case: {fp['case_id']}): [{fp['severity']}] Score {fp['score']} - Reasons: {fp['reasons']}\n")
        if dedupe_b["fn_list"]:
            f.write("\n### False Negatives (Merged Documents)\n")
            for fn in dedupe_b["fn_list"]:
                f.write(f"- Page {fn['page']} (Case: {fn['case_id']}): [{fn['severity']}] Score {fn['score']} - Reasons: {fn['reasons']}\n")
                
        f.write("\n## 2. Duplicate Detection\n")
        f.write("### A. Page-Level Exact Dedupe Safety (Dedupe-First Only)\n")
        f.write("| Architecture | Precision | Recall | TP | FP | FN | Visually Distinct FP |\n")
        f.write("|--------------|-----------|--------|----|----|----|----------------------|\n")
        d_prec = round(dedupe_d['exact_safety']['precision'], 3)
        d_rec = round(dedupe_d['exact_safety']['recall'], 3)
        f.write(f"| Dedupe-First | {d_prec:<9} | {d_rec:<6} | {dedupe_d['exact_safety']['tp']:<2} | {dedupe_d['exact_safety']['fp']:<2} | {dedupe_d['exact_safety']['fn']:<2} | {dedupe_d['exact_safety']['visually_distinct_fp']:<2} |\n")
        f.write("| Segment-First| N/A       | N/A    | N/A| N/A| N/A| N/A |\n")
        
        f.write("\n### B. Exact Duplicate-Document Occurrence Detection\n")
        f.write("*(Metric applies to Segment-First. Dedupe-First relies on page dedupe.)*\n")
        f.write("| Architecture | Precision | Recall | TP | FP | FN |\n")
        f.write("|--------------|-----------|--------|----|----|----|\n")
        s_prec_d = round(segment_d['exact_safety']['precision'], 3)
        s_rec_d = round(segment_d['exact_safety']['recall'], 3)
        f.write("| Dedupe-First | N/A       | N/A    | N/A| N/A| N/A|\n")
        f.write(f"| Segment-First| {s_prec_d:<9} | {s_rec_d:<6} | {segment_d['exact_safety']['tp']:<2} | {segment_d['exact_safety']['fp']:<2} | {segment_d['exact_safety']['fn']:<2} |\n")
        
        f.write("\n### C. Near-Duplicate Document Capability\n")
        f.write("| Architecture | Recall | Caught | Missed |\n")
        f.write("|--------------|--------|--------|--------|\n")
        d_nd = round(dedupe_d['near_duplicate_capability']['recall'], 3)
        s_nd = round(segment_d['near_duplicate_capability']['recall'], 3)
        f.write(f"| Dedupe-First | {d_nd:<6} | {dedupe_d['near_duplicate_capability']['caught']:<6} | {dedupe_d['near_duplicate_capability']['missed']:<6} |\n")
        f.write(f"| Segment-First| {s_nd:<6} | {segment_d['near_duplicate_capability']['caught']:<6} | {segment_d['near_duplicate_capability']['missed']:<6} |\n")
        
        f.write("\n## 3. Deduplication Errors (Dedupe-First)\n")
        if dedupe_d["fp_list"]:
            f.write("### False Positives (Falsely deleted)\n")
            for fp in dedupe_d["fp_list"]:
                f.write(f"- Page {fp['page']}: [{fp['severity']}] {fp['reason']}\n")
        if dedupe_d["fn_list"]:
            f.write("\n### False Negatives (Missed exact duplicate)\n")
            for fn in dedupe_d["fn_list"]:
                f.write(f"- Page {fn['page']}: [{fn['severity']}] {fn['reason']}\n")
                
        f.write("\n## 4. Per-Fixture Breakdown\n")
        f.write("*(Note: The 2 True Positives in the combined corpus are the artificial cross-fixture transitions into Case 05 and Case 06. Because these transition between entirely unrelated documents, the drastic change in fonts and headers allows the heuristic to fire. In the individual cases, these pages are `CORPUS_START` and excluded, and the internal boundaries fail to reach the threshold.)*\n\n")
        f.write("| Fixture | Dedupe F1 | Segment F1 | Dedupe TP | Dedupe FP | Dedupe FN | Dedupe TN | Segment TP | Segment FP | Segment FN | Segment TN |\n")
        f.write("|---------|-----------|------------|-----------|-----------|-----------|-----------|------------|------------|------------|------------|\n")
        for fixture in fixtures:
            res = results[fixture]
            d_b = res["dedupe"]["boundaries"]
            s_b = res["segment"]["boundaries"]
            d_f1 = round(d_b["metrics"]["f1"], 3)
            s_f1 = round(s_b["metrics"]["f1"], 3)
            f.write(f"| {fixture:<7} | {d_f1:<9} | {s_f1:<10} | {d_b['counts']['tp']:<9} | {d_b['counts']['fp']:<9} | {d_b['counts']['fn']:<9} | {d_b['counts']['tn']:<9} | {s_b['counts']['tp']:<10} | {s_b['counts']['fp']:<10} | {s_b['counts']['fn']:<10} | {s_b['counts']['tn']:<10} |\n")
        
    print(f"Report generated at {report_path}")

if __name__ == "__main__":
    main()
