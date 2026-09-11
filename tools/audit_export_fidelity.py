"""Audit every exported page; write structural metadata and hashes only."""
from __future__ import annotations

import argparse
import json
from collections import Counter
from pathlib import Path

import fitz
from pdfresearch.fidelity import compare_pages


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source', type=Path)
    parser.add_argument('output', type=Path)
    parser.add_argument('--render-pages', type=Path, help='JSON array of 1-based source pages')
    parser.add_argument('--segment-ids', type=Path, help='Optional JSON array restricting a repair recheck')
    parser.add_argument('--report-prefix', default='export_fidelity')
    args = parser.parse_args()
    segments = json.loads((args.output / 'manifests/segments.json').read_text())
    if args.segment_ids:
        ids = set(json.loads(args.segment_ids.read_text()))
        segments = [s for s in segments if s['segment_id'] in ids]
    render_pages = set(json.loads(args.render_pages.read_text())) if args.render_pages else set()
    counts = Counter()
    bad = []
    checked = 0
    rendered = 0
    report = args.output / 'manifests' / f'{args.report_prefix}_pages.jsonl'
    with fitz.open(args.source) as source, report.open('w') as handle:
        for index, segment in enumerate(segments, 1):
            path = args.output / f"{segment['category']}/{segment['segment_id']:04d}_{segment['slug']}.pdf"
            pages = segment['canonical_pages']
            mapping = {p-1: i for i, p in enumerate(pages)}
            with fitz.open(path) as out:
                if out.page_count != len(pages):
                    raise ValueError(f"Page count mismatch in segment {segment['segment_id']}")
                for offset, page in enumerate(pages):
                    row = compare_pages(source[page-1], out[offset], page_mapping=mapping,
                                        source_path=args.source, output_path=path, render=page in render_pages)
                    row['segment_id'] = segment['segment_id']
                    checked += 1
                    rendered += page in render_pages
                    counts.update(row['mismatches'])
                    if row['mismatches']:
                        bad.append({'source_page': page, 'segment_id': segment['segment_id'], 'mismatches': row['mismatches']})
                    handle.write(json.dumps(row) + '\n')
            if index % 25 == 0:
                print(f'Audited {index}/{len(segments)} documents; {checked} pages; {len(bad)} mismatching pages', flush=True)
    summary = {'status': 'passed' if not bad else 'failed', 'pages_checked': checked,
               'pages_rendered_72dpi': rendered, 'mismatch_counts': dict(counts), 'mismatching_pages': bad}
    (args.output / 'manifests' / f'{args.report_prefix}_summary.json').write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != 'mismatching_pages'}, indent=2))
    return 1 if bad else 0


if __name__ == '__main__':
    raise SystemExit(main())
