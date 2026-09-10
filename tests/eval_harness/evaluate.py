import json
from pathlib import Path
from pdfresearch.pipeline import run_pipeline

def evaluate_boundaries(decisions_csv: Path, labels: dict[str, str]) -> dict:
    import csv
    tp = fp = fn = tn = 0
    with open(decisions_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            page = row["before_original_page"]
            is_boundary = row["accepted"].lower() == "true"
            truth = labels.get(page)
            if not truth:
                continue
            truth_is_boundary = truth == "BOUNDARY"
            
            if truth_is_boundary and is_boundary:
                tp += 1
            elif not truth_is_boundary and is_boundary:
                fp += 1
            elif truth_is_boundary and not is_boundary:
                fn += 1
            else:
                tn += 1
                
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * (precision * recall) / (precision + recall) if (precision + recall) > 0 else 0.0
    
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": round(precision, 3),
        "recall": round(recall, 3),
        "f1": round(f1, 3)
    }

def evaluate_duplicates(page_map_csv: Path, true_duplicates: dict[str, int]) -> dict:
    import csv
    tp = fp = fn = tn = 0
    predicted_duplicates = {}
    with open(page_map_csv, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            page = str(row["original_page"])
            if row["is_duplicate"].lower() == "true":
                predicted_duplicates[page] = int(row["canonical_page"])
    
    # We want to know if the model correctly identified duplicates and non-duplicates
    # True positives: Page is a duplicate in truth AND predicted as duplicate (and to the right canonical?)
    # False positives: Page is NOT a duplicate in truth BUT predicted as duplicate
    # False negatives: Page IS a duplicate in truth BUT predicted as non-duplicate
    # For now, let's just check duplicate vs non-duplicate.
    # True TN: We don't have all pages here easily unless we read all pages. We can skip TN for dedupe.
    
    for page in predicted_duplicates:
        if page in true_duplicates:
            # Check if mapped to same canonical? For exact dedupe, any earlier page is canonical.
            # We'll just count it as TP if it's marked duplicate.
            tp += 1
        else:
            fp += 1
            
    for page in true_duplicates:
        if page not in predicted_duplicates:
            fn += 1
            
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    
    return {
        "tp": tp, "fp": fp, "fn": fn,
        "precision": round(precision, 3),
        "recall": round(recall, 3)
    }

def run_evaluation():
    data_dir = Path(__file__).parent / "data"
    pdf_path = data_dir / "synthetic_corpus.pdf"
    labels_path = data_dir / "synthetic_labels.json"
    
    with open(labels_path, "r") as f:
        truth = json.load(f)
        
    labels = {str(k): v for k, v in truth["boundaries"].items()}
    true_duplicates = {str(k): v for k, v in truth["duplicates"].items()}

    print("Running Dedupe-First (Default)...")
    out_dir_dedupe = data_dir / "out_dedupe_first"
    run_pipeline(
        pdf_path, out_dir_dedupe,
        rescan=True, write_pdfs=False, write_text=False, segment_first=False
    )
    metrics_dedupe_b = evaluate_boundaries(out_dir_dedupe / "manifests/boundary_review.csv", labels)
    metrics_dedupe_d = evaluate_duplicates(out_dir_dedupe / "manifests/page_map.csv", true_duplicates)
    
    print("\nRunning Segment-First...")
    out_dir_segment = data_dir / "out_segment_first"
    run_pipeline(
        pdf_path, out_dir_segment,
        rescan=True, write_pdfs=False, write_text=False, segment_first=True
    )
    metrics_segment_b = evaluate_boundaries(out_dir_segment / "manifests/boundary_review.csv", labels)
    metrics_segment_d = evaluate_duplicates(out_dir_segment / "manifests/page_map.csv", true_duplicates)

    report = f"""
# A/B Evaluation Report

## Boundaries (Splitting)
| Architecture | Precision | Recall | F1 Score | FP | FN |
|--------------|-----------|--------|----------|----|----|
| Dedupe-First | {metrics_dedupe_b['precision']:<9} | {metrics_dedupe_b['recall']:<6} | {metrics_dedupe_b['f1']:<8} | {metrics_dedupe_b['fp']:<2} | {metrics_dedupe_b['fn']:<2} |
| Segment-First| {metrics_segment_b['precision']:<9} | {metrics_segment_b['recall']:<6} | {metrics_segment_b['f1']:<8} | {metrics_segment_b['fp']:<2} | {metrics_segment_b['fn']:<2} |

## Deduplication (Exact Page Matches)
| Architecture | Precision | Recall | FP | FN |
|--------------|-----------|--------|----|----|
| Dedupe-First | {metrics_dedupe_d['precision']:<9} | {metrics_dedupe_d['recall']:<6} | {metrics_dedupe_d['fp']:<2} | {metrics_dedupe_d['fn']:<2} |
| Segment-First| {metrics_segment_d['precision']:<9} | {metrics_segment_d['recall']:<6} | {metrics_segment_d['fp']:<2} | {metrics_segment_d['fn']:<2} |
"""
    
    report_path = Path(__file__).parent / "ab_report.md"
    with open(report_path, "w") as f:
        f.write(report)
        
    print("\nA/B Report Generated:")
    print(report)

if __name__ == "__main__":
    run_evaluation()
