from __future__ import annotations

from scraper.utils import (
    absolute_url,
    derive_attempt_label,
    ensure_directory,
    guess_filename,
    next_available_path,
    sanitize_component,
)


class TestSanitizeComponent:
    def test_plain_string_unchanged(self):
        assert sanitize_component("homework-1", "fallback") == "homework-1"

    def test_replaces_invalid_chars(self):
        result = sanitize_component('file<>:"/\\|?*name', "fallback")
        assert "<" not in result
        assert ">" not in result
        assert '"' not in result
        assert "/" not in result

    def test_collapses_internal_whitespace(self):
        assert sanitize_component("hello   world", "fallback") == "hello world"

    def test_empty_string_returns_fallback(self):
        assert sanitize_component("", "fallback") == "fallback"

    def test_only_dots_returns_fallback(self):
        assert sanitize_component("...", "fallback") == "fallback"

    def test_strips_leading_trailing_dots(self):
        result = sanitize_component("...hello...", "fallback")
        assert not result.startswith(".")
        assert not result.endswith(".")


class TestAbsoluteUrl:
    def test_relative_path_with_leading_slash(self):
        assert absolute_url("https://example.com", "/courses/1") == "https://example.com/courses/1"

    def test_already_absolute_url_unchanged(self):
        url = "https://other.example.com/page"
        assert absolute_url("https://example.com", url) == url

    def test_relative_path_without_leading_slash(self):
        result = absolute_url("https://example.com/base/", "page")
        assert result == "https://example.com/base/page"


class TestGuessFilename:
    def test_url_with_extension(self):
        result = guess_filename("https://example.com/submission.pdf", "", "artifact.bin")
        assert result == "submission.pdf"

    def test_url_query_param_filename(self):
        result = guess_filename("https://example.com/download?filename=report.pdf", "", "artifact.bin")
        assert result == "report.pdf"

    def test_link_text_with_embedded_filename(self):
        result = guess_filename("https://example.com/download", "Download report.pdf here", "artifact.bin")
        assert result == "report.pdf"

    def test_fallback_when_no_hint(self):
        result = guess_filename("https://example.com/download", "", "artifact.bin")
        assert result == "artifact.bin"

    def test_prefers_url_path_over_link_text(self):
        result = guess_filename("https://example.com/submission.pdf", "link-text.pdf", "artifact.bin")
        assert result == "submission.pdf"

    def test_alternative_query_keys(self):
        result = guess_filename("https://example.com/download?file=notes.pdf", "", "artifact.bin")
        assert result == "notes.pdf"


class TestDeriveAttemptLabel:
    def test_extracts_submission_id(self):
        url = "https://example.com/courses/1/assignments/2/submissions/999"
        assert derive_attempt_label(url) == "submission-999"

    def test_no_submission_returns_default(self):
        url = "https://example.com/courses/1/assignments/2"
        assert derive_attempt_label(url) == "assignment-page"


class TestNextAvailablePath:
    def test_returns_original_when_not_exists(self, tmp_path):
        p = tmp_path / "file.pdf"
        assert next_available_path(p) == p

    def test_increments_when_file_exists(self, tmp_path):
        p = tmp_path / "file.pdf"
        p.write_bytes(b"data")
        result = next_available_path(p)
        assert result == tmp_path / "file__2.pdf"

    def test_increments_twice_when_two_exist(self, tmp_path):
        p = tmp_path / "file.pdf"
        p.write_bytes(b"data")
        (tmp_path / "file__2.pdf").write_bytes(b"data")
        result = next_available_path(p)
        assert result == tmp_path / "file__3.pdf"


class TestEnsureDirectory:
    def test_creates_nested_directory(self, tmp_path):
        new_dir = tmp_path / "a" / "b" / "c"
        assert not new_dir.exists()
        ensure_directory(new_dir)
        assert new_dir.is_dir()

    def test_existing_directory_raises_no_error(self, tmp_path):
        ensure_directory(tmp_path)
        assert tmp_path.is_dir()
