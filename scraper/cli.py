from __future__ import annotations

import argparse
from pathlib import Path

from scraper.config import ScraperConfig
from scraper.gradescope import run_scraper


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="gradescope-scraper",
        description="Archive Gradescope graded-copy PDFs.",
    )
    parser.add_argument(
        "--base-url",
        default="https://www.gradescope.ca",
        help="Gradescope base URL (default: https://www.gradescope.ca).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path("archive"),
        help="Output archive directory (default: archive).",
    )
    parser.add_argument(
        "--state",
        type=Path,
        default=Path(".auth") / "storage_state.json",
        help="Path to persisted browser auth state.",
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=None,
        help="Manifest path (default: <out>/manifest.json).",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run browser in headless mode. Omit for interactive login.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-download files even when manifest says they already exist.",
    )
    parser.add_argument(
        "--login-only",
        action="store_true",
        help="Only authenticate and save session state, then exit.",
    )
    parser.add_argument(
        "--max-retries",
        type=int,
        default=3,
        help="Max download retries for transient failures.",
    )
    parser.add_argument(
        "--timeout-ms",
        type=int,
        default=120000,
        help="Navigation/request timeout in milliseconds (default: 120000).",
    )
    parser.add_argument(
        "--course-id",
        dest="course_ids",
        action="append",
        default=[],
        help="Optional course id filter. Repeat for multiple course ids.",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    manifest_path = args.manifest if args.manifest else args.out / "manifest.json"

    config = ScraperConfig(
        base_url=args.base_url.rstrip("/"),
        output_dir=args.out,
        state_path=args.state,
        manifest_path=manifest_path,
        headless=bool(args.headless),
        force=bool(args.force),
        login_only=bool(args.login_only),
        max_retries=max(1, int(args.max_retries)),
        timeout_ms=max(5000, int(args.timeout_ms)),
        course_ids=[str(course_id).strip() for course_id in args.course_ids if str(course_id).strip()],
    )

    summary = run_scraper(config)
    print(
        "Done. "
        f"courses={summary.courses}, assignments={summary.assignments}, "
        f"links={summary.discovered_links}, downloaded={summary.downloaded}, skipped={summary.skipped}, failed={summary.failed}"
    )
    return 0
