from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .pipeline import run_pipeline


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="pdfresearch",
        description="Local-first dedupe and document-boundary recovery for huge merged PDFs.",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    run = sub.add_parser("run", help="scan, dedupe, segment and optionally write split PDFs")
    run.add_argument("input_pdf", type=Path)
    run.add_argument("--output", type=Path, default=Path("pdfresearch-output"))
    run.add_argument("--boundary-threshold", type=float, default=5.0)
    run.add_argument("--min-text-for-text-hash", type=int, default=80)
    run.add_argument("--config", type=Path, default=None, help="optional TOML overrides")
    run.add_argument("--rescan", action="store_true", help="discard page cache and scan from page 1")
    run.add_argument("--no-pdfs", action="store_true", help="build manifests/text only")
    run.add_argument("--no-text", action="store_true", help="do not write per-segment .txt files")
    run.add_argument("--segment-first", action="store_true", help="preserve all original pages when splitting; report page and document duplicates without deleting them")
    run.add_argument(
        "--write-deduped-pdf",
        action="store_true",
        help="also write one monolithic deduplicated.pdf (can be large)",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command != "run":
        parser.error("unknown command")

    if not args.input_pdf.exists():
        parser.error(f"input PDF does not exist: {args.input_pdf}")
    if args.input_pdf.suffix.casefold() != ".pdf":
        parser.error("input must be a .pdf file")
    if args.min_text_for_text_hash < 0:
        parser.error("--min-text-for-text-hash must be >= 0")

    try:
        stats = run_pipeline(
            args.input_pdf,
            args.output,
            boundary_threshold=args.boundary_threshold,
            min_text_for_text_hash=args.min_text_for_text_hash,
            config_path=args.config,
            rescan=args.rescan,
            write_pdfs=not args.no_pdfs,
            write_text=not args.no_text,
            write_deduped_pdf=args.write_deduped_pdf,
            segment_first=args.segment_first,
        )
    except KeyboardInterrupt:
        print("Interrupted. The page scan cache is resumable; rerun the same command.", file=sys.stderr)
        return 130
    except Exception as exc:
        print(f"pdfresearch failed: {exc}", file=sys.stderr)
        return 1

    print("\nCompleted")
    print(json.dumps(stats, indent=2))
    print(f"\nReview manifests under: {args.output / 'manifests'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
