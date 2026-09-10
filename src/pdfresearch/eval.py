import csv
from pathlib import Path
from pdfresearch.pipeline import run_pipeline

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
    
    with open(decisions_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            page = int(row["before_original_page"])
            is_boundary = row["accepted"].lower() == "true"
            score = row["score"]
            reasons = row["reasons"]
            
            label = truth.get(page, "UNCERTAIN")
            if label == "UNCERTAIN":
                continue
                
            truth_is_boundary = label == "BOUNDARY"
            
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
            "precision": round(precision, 3),
            "recall": round(recall, 3),
            "tp": exact_tp, "fp": exact_fp, "fn": exact_fn,
            "visually_distinct_fp": visually_distinct_fp
        },
        "near_duplicate_capability": {
            "recall": round(near_dup_recall, 3),
            "caught": near_dup_caught,
            "missed": near_dup_missed
        },
        "fp_list": fp_list,
        "fn_list": fn_list
    }

def main():
    import subprocess
    try:
        git_sha = subprocess.check_output(["git", "rev-parse", "HEAD"]).decode("utf-8").strip()
    except Exception:
        git_sha = "unknown"
        
    fixture_version = "v1.0"
    evaluator_version = "v1.0"
    
    root = Path(__file__).parent.parent.parent
    data_dir = root / "tests" / "eval_harness" / "data"
    pdf_path = data_dir / "combined_corpus.pdf"
    boundaries_csv = data_dir / "combined_corpus_boundaries.csv"
    duplicates_csv = data_dir / "combined_corpus_duplicates.csv"
    
    if not pdf_path.exists():
        print("Fixtures not found. Please run tests/eval_harness/generate_fixtures.py first.")
        return
        
    print("Evaluating Dedupe-First Architecture...")
    out_dedupe = data_dir / "out_dedupe"
    run_pipeline(pdf_path, out_dedupe, rescan=True, write_pdfs=False, write_text=False, segment_first=False)
    dedupe_b = evaluate_boundaries(out_dedupe / "manifests/boundary_review.csv", boundaries_csv)
    dedupe_d = evaluate_duplicates(out_dedupe / "manifests/page_map.csv", duplicates_csv)
    
    print("Evaluating Segment-First Architecture...")
    out_segment = data_dir / "out_segment"
    run_pipeline(pdf_path, out_segment, rescan=True, write_pdfs=False, write_text=False, segment_first=True)
    segment_b = evaluate_boundaries(out_segment / "manifests/boundary_review.csv", boundaries_csv)
    segment_d = evaluate_duplicates(out_segment / "manifests/page_map.csv", duplicates_csv)
    
    report_path = root / "eval_baseline_report.md"
    with open(report_path, "w", encoding="utf-8") as f:
        f.write("# Baseline Synthetic Evaluation Report (v1)\n\n")
        f.write(f"- **Git SHA**: `{git_sha}`\n")
        f.write(f"- **Fixture Version**: `{fixture_version}`\n")
        f.write(f"- **Evaluator Version**: `{evaluator_version}`\n\n")
        
        f.write("## Boundary Detection\n")
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
                
        f.write("\n## Duplicate Detection\n")
        f.write("### Exact Dedupe Safety\n")
        f.write("| Architecture | Precision | Recall | TP | FP | FN | Visually Distinct FP |\n")
        f.write("|--------------|-----------|--------|----|----|----|----------------------|\n")
        f.write(f"| Dedupe-First | {dedupe_d['exact_safety']['precision']:<9} | {dedupe_d['exact_safety']['recall']:<6} | {dedupe_d['exact_safety']['tp']:<2} | {dedupe_d['exact_safety']['fp']:<2} | {dedupe_d['exact_safety']['fn']:<2} | {dedupe_d['exact_safety']['visually_distinct_fp']:<2} |\n")
        f.write(f"| Segment-First| {segment_d['exact_safety']['precision']:<9} | {segment_d['exact_safety']['recall']:<6} | {segment_d['exact_safety']['tp']:<2} | {segment_d['exact_safety']['fp']:<2} | {segment_d['exact_safety']['fn']:<2} | {segment_d['exact_safety']['visually_distinct_fp']:<2} |\n")
        
        f.write("\n### Near-Duplicate Capability\n")
        f.write("| Architecture | Recall | Caught | Missed |\n")
        f.write("|--------------|--------|--------|--------|\n")
        f.write(f"| Dedupe-First | {dedupe_d['near_duplicate_capability']['recall']:<6} | {dedupe_d['near_duplicate_capability']['caught']:<6} | {dedupe_d['near_duplicate_capability']['missed']:<6} |\n")
        f.write(f"| Segment-First| {segment_d['near_duplicate_capability']['recall']:<6} | {segment_d['near_duplicate_capability']['caught']:<6} | {segment_d['near_duplicate_capability']['missed']:<6} |\n")
        
        f.write("\n## Deduplication Errors (Dedupe-First)\n")
        if dedupe_d["fp_list"]:
            f.write("### False Positives (Falsely deleted)\n")
            for fp in dedupe_d["fp_list"]:
                f.write(f"- Page {fp['page']}: [{fp['severity']}] {fp['reason']}\n")
        if dedupe_d["fn_list"]:
            f.write("\n### False Negatives (Missed exact duplicate)\n")
            for fn in dedupe_d["fn_list"]:
                f.write(f"- Page {fn['page']}: [{fn['severity']}] {fn['reason']}\n")
        
    print(f"Report generated at {report_path}")

if __name__ == "__main__":
    main()
