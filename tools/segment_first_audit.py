from __future__ import annotations

import argparse
import json
from pathlib import Path

from pdfresearch.segment_first import run_segment_first_audit


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Compare the current dedupe-first segmentation with a safer "
            "segment-first/document-dedupe audit path."
        )
    )
    parser.add_argument("source", type=Path, help="Merged source PDF")
    parser.add_argument("--output", type=Path, default=Path("pdfresearch-output"))
    parser.add_argument("--boundary-threshold", type=float, default=5.0)
    parser.add_argument("--min-text-for-text-hash", type=int, default=80)
    parser.add_argument("--config", type=Path, default=None)
    parser.add_argument("--rescan", action="store_true")
    args = parser.parse_args()

    result = run_segment_first_audit(
        args.source,
        args.output,
        boundary_threshold=args.boundary_threshold,
        min_text_for_text_hash=args.min_text_for_text_hash,
        config_path=args.config,
        rescan=args.rescan,
    )
    print(json.dumps({k: v for k, v in result.items() if k != "segments"}, indent=2))
    print(f"audit: {args.output / 'manifests' / 'segment_first_audit.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
