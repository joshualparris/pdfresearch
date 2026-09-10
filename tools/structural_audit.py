"""Create a local structural audit without titles, extracted text or identifiers."""
from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path

from pdfresearch.fidelity import digest
from pdfresearch.models import PageRecord
from pdfresearch.signals import score_boundary


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    args = parser.parse_args()
    root = args.output
    records = [PageRecord.from_json(json.loads(line)) for line in (root / '.cache/pages.jsonl').open()]
    segments = json.loads((root / 'manifests/segments.json').read_text())
    occurrences = json.loads((root / 'manifests/document_occurrences.json').read_text())
    accepted = {s['original_start'] for s in segments}
    groups = defaultdict(list)
    for r in records:
        groups[r.duplicate_of or r.original_page].append(r.original_page)
    boundaries = []
    for a, b in zip(records, records[1:]):
        score = score_boundary(a, b)
        boundaries.append({'before_original_page': b.original_page, 'unconfigured_score': score.score,
                           'unconfigured_reasons': score.reasons, 'accepted_in_current_run': b.original_page in accepted})
    docs = []
    for s, o in zip(segments, occurrences):
        assert s['segment_id'] == o['segment_id']
        reason = s['category_reason']
        if 'pattern:' in reason:
            reason = 'configuration_pattern_sha256:' + digest(reason)
        docs.append({'segment_id': s['segment_id'], 'original_start': s['original_start'],
                     'original_end': s['original_end'], 'page_count': s['page_count'],
                     'boundary_score': s['boundary_score'], 'boundary_reasons': s['boundary_reasons'],
                     'category': s['category'], 'category_reason': reason,
                     'document_fingerprint': o['fingerprint'], 'duplicate_of_segment_id': o['duplicate_of_segment_id']})
    baseline_path = root / 'baseline-manifests/segments.json'
    baseline = {s['original_start'] for s in json.loads(baseline_path.read_text())} if baseline_path.exists() else set()
    result = {
        'interpretation': 'Current algorithm and local review results, not ground truth. Hash equality is not visual identity.',
        'stats': json.loads((root / 'manifests/stats.json').read_text()),
        'boundaries': boundaries, 'documents': docs,
        'duplicate_groups': [{'canonical_page': p, 'group_size_including_canonical': len(v), 'pages': v}
                             for p, v in sorted(groups.items()) if len(v) > 1],
        'boundary_disagreement_with_default_dedupe_first': {
            'added_starts': sorted(accepted - baseline), 'removed_starts': sorted(baseline - accepted),
        },
    }
    path = root / 'manifests/structural_audit.json'
    path.write_text(json.dumps(result, indent=2))
    print(f'Wrote {len(docs)} structural document records and {len(boundaries)} boundary decisions')


if __name__ == '__main__':
    main()
