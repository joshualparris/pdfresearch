import tempfile
from pathlib import Path
import csv
from pdfresearch.eval import evaluate_boundaries, evaluate_duplicates, evaluate_document_occurrences

def test_evaluate_boundaries():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir = Path(tmp_dir)
        labels_csv = tmp_dir / "labels.csv"
        decisions_csv = tmp_dir / "decisions.csv"
        
        with open(labels_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["before_page", "label", "case_id", "notes"])
            # TP (Predicted BOUNDARY, Truth BOUNDARY)
            writer.writerow([2, "BOUNDARY", "c1", ""])
            # TN (Predicted CONTINUATION, Truth CONTINUATION)
            writer.writerow([3, "CONTINUATION", "c1", ""])
            # FP (Predicted BOUNDARY, Truth CONTINUATION)
            writer.writerow([4, "CONTINUATION", "c1", ""])
            # FN (Predicted CONTINUATION, Truth BOUNDARY)
            writer.writerow([5, "BOUNDARY", "c1", ""])
            # UNCERTAIN excluded
            writer.writerow([6, "UNCERTAIN", "c1", ""])
            # Ignored page (not in predictions, but truth says boundary)
            writer.writerow([7, "BOUNDARY", "c1", ""])
            # Ignored page (not in predictions, truth says continuation)
            writer.writerow([8, "CONTINUATION", "c1", ""])
            
        with open(decisions_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["before_original_page", "accepted", "score", "reasons"])
            writer.writerow([2, "True", "10", ""])
            writer.writerow([3, "False", "-5", ""])
            writer.writerow([4, "True", "6", ""])
            writer.writerow([5, "False", "2", ""])
            writer.writerow([6, "True", "10", ""])  # Should be excluded
            # Page 7 and 8 have NO prediction rows

        res = evaluate_boundaries(decisions_csv, labels_csv)
        counts = res["counts"]
        # Expected counts (page 2 is TP, 3 is TN, 4 is FP, 5 is FN, 
        # 7 is FN because it's completely missing, 8 is TN because it's completely missing)
        assert counts["tp"] == 1
        assert counts["tn"] == 2
        assert counts["fp"] == 1
        assert counts["fn"] == 2
        # UNCERTAIN (page 6) should not be counted
        assert sum(counts.values()) == 6
        
        # Precision = TP / (TP + FP) = 1 / (1 + 1) = 0.5
        # Recall = TP / (TP + FN) = 1 / (1 + 2) = 0.333
        # F1 = 2 * (0.5 * 0.333) / (0.5 + 0.333) = 0.4
        assert round(res["metrics"]["precision"], 3) == 0.5
        assert round(res["metrics"]["recall"], 3) == 0.333
        assert round(res["metrics"]["f1"], 3) == 0.4
            
        # Zero denominator test
        with open(labels_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["before_page", "label", "case_id", "notes"])
        with open(decisions_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["before_original_page", "accepted", "score", "reasons"])
        res_zero = evaluate_boundaries(decisions_csv, labels_csv)
        assert res_zero["metrics"]["precision"] == 0.0
        assert res_zero["metrics"]["recall"] == 0.0
        assert res_zero["metrics"]["f1"] == 0.0

def test_evaluate_duplicates():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir = Path(tmp_dir)
        labels_csv = tmp_dir / "labels.csv"
        page_map_csv = tmp_dir / "page_map.csv"
        
        with open(labels_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["page", "canonical_page", "type"])
            # EXACT_DUPLICATE correctly predicted
            writer.writerow([2, 1, "EXACT_DUPLICATE"])
            # EXACT_DUPLICATE missed (FN)
            writer.writerow([3, 1, "EXACT_DUPLICATE"])
            # SAME_TEXT_VISUALLY_DISTINCT incorrectly predicted (FP for exact safety)
            writer.writerow([4, 1, "SAME_TEXT_VISUALLY_DISTINCT"])
            # NEAR_DUPLICATE correctly predicted (Caught) - shouldn't affect Exact Dedupe
            writer.writerow([5, 1, "NEAR_DUPLICATE"])
            # NEAR_DUPLICATE missed (Missed) - shouldn't affect Exact Dedupe FN
            writer.writerow([6, 1, "NEAR_DUPLICATE"])
            # DISTINCT incorrectly predicted (FP)
            writer.writerow([7, 1, "DISTINCT"])
            
        with open(page_map_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["original_page", "canonical_page", "is_duplicate"])
            writer.writerow([2, 1, "True"])
            writer.writerow([3, 1, "False"])
            writer.writerow([4, 1, "True"])
            writer.writerow([5, 1, "True"])
            writer.writerow([6, 1, "False"])
            writer.writerow([7, 1, "True"])
            # Unlisted in truth, defaults to DISTINCT. Not predicted duplicate -> TN (ignored).
            writer.writerow([8, 1, "False"])
            
        res = evaluate_duplicates(page_map_csv, labels_csv)
        exact = res["exact_safety"]
        near = res["near_duplicate_capability"]
        
        # EXACT_DUPLICATE: TP = page 2 (1), FN = page 3 (1)
        # FP: page 4 (visually distinct), page 7 (distinct)
        assert exact["tp"] == 1
        assert exact["fn"] == 1
        assert exact["fp"] == 2
        assert exact["visually_distinct_fp"] == 1
        
        # Precision = 1 / (1 + 2) = 0.333
        # Recall = 1 / (1 + 1) = 0.500
        assert round(exact["precision"], 3) == 0.333
        assert round(exact["recall"], 3) == 0.500
        
        # Near duplicate: page 5 caught, page 6 missed
        assert near["caught"] == 1
        assert near["missed"] == 1
        assert near["recall"] == 0.500
        
        # Zero denominator test
        with open(labels_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["page", "canonical_page", "type"])
        with open(page_map_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["original_page", "canonical_page", "is_duplicate"])
        res_zero = evaluate_duplicates(page_map_csv, labels_csv)
        assert res_zero["exact_safety"]["precision"] == 0.0
        assert res_zero["exact_safety"]["recall"] == 0.0
        assert res_zero["near_duplicate_capability"]["recall"] == 0.0

class MockOccurrence:
    def __init__(self, original_start, duplicate_of_segment_id=None):
        self.original_start = original_start
        self.duplicate_of_segment_id = duplicate_of_segment_id

def test_evaluate_document_occurrences():
    with tempfile.TemporaryDirectory() as tmp_dir:
        tmp_dir = Path(tmp_dir)
        doc_labels_csv = tmp_dir / "doc_labels.csv"
        
        with open(doc_labels_csv, "w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["start_page", "canonical_start_page", "type"])
            # EXACT_DUPLICATE_DOCUMENT correctly predicted
            writer.writerow([2, 1, "EXACT_DUPLICATE_DOCUMENT"])
            # EXACT_DUPLICATE_DOCUMENT missed (FN)
            writer.writerow([3, 1, "EXACT_DUPLICATE_DOCUMENT"])
            # NEAR_DUPLICATE_DOCUMENT correctly predicted (Caught)
            writer.writerow([4, 1, "NEAR_DUPLICATE_DOCUMENT"])
            # NEAR_DUPLICATE_DOCUMENT missed (Missed)
            writer.writerow([5, 1, "NEAR_DUPLICATE_DOCUMENT"])
            # DISTINCT incorrectly predicted (FP)
            writer.writerow([6, 1, "DISTINCT"])
            
        occurrences = [
            MockOccurrence(2, "some_id"),   # TP exact
            MockOccurrence(3, None),        # FN exact
            MockOccurrence(4, "some_id"),   # Caught near
            MockOccurrence(5, None),        # Missed near
            MockOccurrence(6, "some_id"),   # FP exact
            MockOccurrence(7, None),        # TN
        ]
        
        res = evaluate_document_occurrences(occurrences, doc_labels_csv)
        exact = res["exact_safety"]
        near = res["near_duplicate_capability"]
        
        assert exact["tp"] == 1
        assert exact["fn"] == 1
        assert exact["fp"] == 1
        assert round(exact["precision"], 3) == 0.500
        assert round(exact["recall"], 3) == 0.500
        
        assert near["caught"] == 1
        assert near["missed"] == 1
        assert round(near["recall"], 3) == 0.500

if __name__ == "__main__":
    test_evaluate_boundaries()
    test_evaluate_duplicates()
    test_evaluate_document_occurrences()
    print("Self-tests passed.")
