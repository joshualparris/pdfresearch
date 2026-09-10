# Baseline Synthetic Evaluation Report (v1)

- **Evaluated Code SHA**: `7f7533c3c865f19cfdc082a8499f85484bdd370b`
- **Fixture Version**: `v1.1`
- **Evaluator Version**: `v1.1`

## 1. Aggregate Results (Combined Corpus)

| Architecture | Precision | Recall | F1 Score | TP | FP | FN | TN |
|--------------|-----------|--------|----------|----|----|----|----|
| Dedupe-First | 1.0       | 0.111  | 0.2      | 2  | 0  | 16 | 12 |
| Segment-First| 0.0       | 0.0    | 0.0      | 0  | 0  | 18 | 12 |

## Boundary Errors (Dedupe-First)

### False Negatives (Merged Documents)
- Page 4 (Case: case_02): [HIGH] Score 3.1 - Reasons: running_header_weak_match|strong_title_typography|cover_like_page
- Page 6 (Case: case_02): [HIGH] Score 2.95 - Reasons: font_signature_changes|strong_title_typography|cover_like_page
- Page 7 (Case: case_03): [HIGH] Score 1.95 - Reasons: running_header_changes|font_signature_changes
- Page 8 (Case: case_03): [HIGH] Score N/A - Reasons: Page deleted before segmentation
- Page 9 (Case: case_04): [HIGH] Score 4.45 - Reasons: small_original_gap:2|running_header_changes|font_signature_changes|title_typography|cover_like_page
- Page 13 (Case: case_05): [HIGH] Score N/A - Reasons: Page deleted before segmentation
- Page 17 (Case: case_06): [HIGH] Score 3.15 - Reasons: running_header_weak_match|running_footer_continues|font_signature_changes|strong_title_typography|cover_like_page
- Page 19 (Case: case_07): [HIGH] Score 2.05 - Reasons: font_signature_changes|title_typography|cover_like_page
- Page 22 (Case: case_08): [HIGH] Score N/A - Reasons: Page deleted before segmentation
- Page 23 (Case: case_08): [HIGH] Score 3.05 - Reasons: small_original_gap:2|font_signature_changes|title_typography|cover_like_page
- Page 24 (Case: case_09): [HIGH] Score -0.6 - Reasons: running_header_continues|title_typography|cover_like_page|strong_continuity_bundle
- Page 26 (Case: case_10): [HIGH] Score 1.55 - Reasons: small_original_gap:2|font_signature_changes
- Page 27 (Case: case_10): [HIGH] Score 0.3 - Reasons: page_number_resets|running_header_continues|strong_continuity_bundle
- Page 28 (Case: case_11): [HIGH] Score 1.4 - Reasons: running_header_changes
- Page 30 (Case: case_12): [HIGH] Score 4.35 - Reasons: running_header_changes|font_signature_changes|strong_title_typography|cover_like_page
- Page 31 (Case: case_12): [HIGH] Score 0.3 - Reasons: running_header_continues|strong_title_typography|cover_like_page|strong_continuity_bundle

## Duplicate Detection
### Exact Dedupe Safety
| Architecture | Precision | Recall | TP | FP | FN | Visually Distinct FP |
|--------------|-----------|--------|----|----|----|----------------------|
| Dedupe-First | 0.5       | 1.0    | 3  | 3  | 0  | 1  |
| Segment-First| 0.0       | 0.0    | 0  | 0  | 3  | 0  |

### Near-Duplicate Capability
| Architecture | Recall | Caught | Missed |
|--------------|--------|--------|--------|
| Dedupe-First | 0.0    | 0      | 2      |
| Segment-First| 0.0    | 0      | 2      |

## 2. Deduplication Errors (Dedupe-First)
### False Positives (Falsely deleted)
- Page 8: [CRITICAL] Falsely deduped visually distinct page
- Page 22: [HIGH] Falsely deduped distinct page
- Page 25: [HIGH] Falsely deduped distinct page

## 3. Per-Fixture Breakdown
| Fixture | Dedupe F1 | Segment F1 | Dedupe Exact Recall | Segment Exact Recall |
|---------|-----------|------------|---------------------|----------------------|
| case_01 | 0.0       | 0.0        | 0.0                 | 0.0                  |
| case_02 | 0.0       | 0.0        | 0.0                 | 0.0                  |
| case_03 | 0.0       | 0.0        | 0.0                 | 0.0                  |
| case_04 | 0.0       | 0.0        | 1.0                 | 0.0                  |
| case_05 | 0.0       | 0.0        | 1.0                 | 0.0                  |
| case_06 | 0.0       | 0.0        | 0.0                 | 0.0                  |
| case_07 | 0.0       | 0.0        | 0.0                 | 0.0                  |
| case_08 | 0.0       | 0.0        | 0.0                 | 0.0                  |
| case_09 | 0.0       | 0.0        | 0.0                 | 0.0                  |
| case_10 | 0.0       | 0.0        | 0.0                 | 0.0                  |
| case_11 | 0.0       | 0.0        | 0.0                 | 0.0                  |
| case_12 | 0.0       | 0.0        | 0.0                 | 0.0                  |
