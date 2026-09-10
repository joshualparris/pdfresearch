# Baseline Synthetic Evaluation Report (v1)

- **Git SHA**: `1106bdf4f07d68b85e57b282dbe0e4c0b3f39fc5`
- **Fixture Version**: `v1.0`
- **Evaluator Version**: `v1.0`

## Boundary Detection
| Architecture | Precision | Recall | F1 Score | TP | FP | FN | TN |
|--------------|-----------|--------|----------|----|----|----|----|
| Dedupe-First | 1.0       | 0.133  | 0.235    | 2  | 0  | 13 | 9  |
| Segment-First| 0.0       | 0.0    | 0.0      | 0  | 0  | 18 | 12 |

## Boundary Errors (Dedupe-First)

### False Negatives (Merged Documents)
- Page 4 (Case: case_2): [HIGH] Score 3.1 - Reasons: running_header_weak_match|strong_title_typography|cover_like_page
- Page 6 (Case: case_2): [HIGH] Score 2.95 - Reasons: font_signature_changes|strong_title_typography|cover_like_page
- Page 7 (Case: case_3): [HIGH] Score 1.95 - Reasons: running_header_changes|font_signature_changes
- Page 9 (Case: case_4): [HIGH] Score 4.45 - Reasons: small_original_gap:2|running_header_changes|font_signature_changes|title_typography|cover_like_page
- Page 17 (Case: case_6): [HIGH] Score 3.15 - Reasons: running_header_weak_match|running_footer_continues|font_signature_changes|strong_title_typography|cover_like_page
- Page 19 (Case: case_7): [HIGH] Score 2.05 - Reasons: font_signature_changes|title_typography|cover_like_page
- Page 23 (Case: case_8): [HIGH] Score 3.05 - Reasons: small_original_gap:2|font_signature_changes|title_typography|cover_like_page
- Page 24 (Case: case_9): [HIGH] Score -0.6 - Reasons: running_header_continues|title_typography|cover_like_page|strong_continuity_bundle
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
| Segment-First| 0.5       | 1.0    | 3  | 3  | 0  | 1  |

### Near-Duplicate Capability
| Architecture | Recall | Caught | Missed |
|--------------|--------|--------|--------|
| Dedupe-First | 0.0    | 0      | 2      |
| Segment-First| 0.0    | 0      | 2      |

## Deduplication Errors (Dedupe-First)
### False Positives (Falsely deleted)
- Page 8: [CRITICAL] Falsely deduped visually distinct page
- Page 22: [HIGH] Falsely deduped distinct page
- Page 25: [HIGH] Falsely deduped distinct page
