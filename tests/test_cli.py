from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from scraper.cli import build_parser, main
from scraper.models import RunSummary


class TestBuildParser:
    def test_defaults(self):
        parser = build_parser()
        args = parser.parse_args([])
        assert args.base_url == "https://www.gradescope.ca"
        assert args.out == Path("archive")
        assert args.state == Path(".auth") / "storage_state.json"
        assert args.manifest is None
        assert args.headless is False
        assert args.force is False
        assert args.login_only is False
        assert args.max_retries == 3
        assert args.timeout_ms == 120000
        assert args.course_ids == []

    def test_custom_base_url(self):
        args = build_parser().parse_args(["--base-url", "https://custom.gradescope.com"])
        assert args.base_url == "https://custom.gradescope.com"

    def test_custom_out(self):
        args = build_parser().parse_args(["--out", "/tmp/my-archive"])
        assert args.out == Path("/tmp/my-archive")

    def test_headless_flag(self):
        args = build_parser().parse_args(["--headless"])
        assert args.headless is True

    def test_force_flag(self):
        args = build_parser().parse_args(["--force"])
        assert args.force is True

    def test_login_only_flag(self):
        args = build_parser().parse_args(["--login-only"])
        assert args.login_only is True

    def test_multiple_course_ids(self):
        args = build_parser().parse_args(["--course-id", "123", "--course-id", "456"])
        assert "123" in args.course_ids
        assert "456" in args.course_ids

    def test_max_retries(self):
        args = build_parser().parse_args(["--max-retries", "5"])
        assert args.max_retries == 5

    def test_timeout_ms(self):
        args = build_parser().parse_args(["--timeout-ms", "60000"])
        assert args.timeout_ms == 60000

    def test_custom_manifest(self):
        args = build_parser().parse_args(["--manifest", "/tmp/my-manifest.json"])
        assert args.manifest == Path("/tmp/my-manifest.json")

    def test_custom_state(self):
        args = build_parser().parse_args(["--state", "/tmp/state.json"])
        assert args.state == Path("/tmp/state.json")


class TestMain:
    def test_returns_zero_on_success(self):
        summary = RunSummary(courses=1, assignments=2, downloaded=3, skipped=0, failed=0, discovered_links=3)
        with patch("scraper.cli.run_scraper", return_value=summary):
            with patch("sys.argv", ["gradescope-scraper"]):
                result = main()
        assert result == 0

    def test_manifest_defaults_to_out_dir(self):
        captured = {}

        def capture_config(config):
            captured["config"] = config
            return RunSummary()

        with patch("scraper.cli.run_scraper", side_effect=capture_config):
            with patch("sys.argv", ["gradescope-scraper", "--out", "/tmp/test-archive"]):
                main()

        assert captured["config"].manifest_path == Path("/tmp/test-archive") / "manifest.json"

    def test_explicit_manifest_used(self):
        captured = {}

        def capture_config(config):
            captured["config"] = config
            return RunSummary()

        with patch("scraper.cli.run_scraper", side_effect=capture_config):
            with patch("sys.argv", ["gradescope-scraper", "--manifest", "/tmp/custom.json"]):
                main()

        assert captured["config"].manifest_path == Path("/tmp/custom.json")

    def test_base_url_trailing_slash_stripped(self):
        captured = {}

        def capture_config(config):
            captured["config"] = config
            return RunSummary()

        with patch("scraper.cli.run_scraper", side_effect=capture_config):
            with patch("sys.argv", ["gradescope-scraper", "--base-url", "https://www.gradescope.ca/"]):
                main()

        assert not captured["config"].base_url.endswith("/")

    def test_max_retries_enforces_minimum_of_one(self):
        captured = {}

        def capture_config(config):
            captured["config"] = config
            return RunSummary()

        with patch("scraper.cli.run_scraper", side_effect=capture_config):
            with patch("sys.argv", ["gradescope-scraper", "--max-retries", "0"]):
                main()

        assert captured["config"].max_retries >= 1

    def test_timeout_ms_enforces_minimum(self):
        captured = {}

        def capture_config(config):
            captured["config"] = config
            return RunSummary()

        with patch("scraper.cli.run_scraper", side_effect=capture_config):
            with patch("sys.argv", ["gradescope-scraper", "--timeout-ms", "1"]):
                main()

        assert captured["config"].timeout_ms >= 5000

    def test_course_ids_blank_entries_filtered(self):
        captured = {}

        def capture_config(config):
            captured["config"] = config
            return RunSummary()

        with patch("scraper.cli.run_scraper", side_effect=capture_config):
            with patch("sys.argv", ["gradescope-scraper", "--course-id", "  ", "--course-id", "123"]):
                main()

        assert "  " not in captured["config"].course_ids
        assert "123" in captured["config"].course_ids
