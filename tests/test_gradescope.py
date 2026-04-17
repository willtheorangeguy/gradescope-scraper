from __future__ import annotations

from urllib.parse import quote

from scraper.gradescope import ensure_pdf_name, expand_candidate_urls


class TestEnsurePdfName:
    def test_already_has_pdf_extension(self):
        assert ensure_pdf_name("graded-copy.pdf") == "graded-copy.pdf"

    def test_adds_pdf_extension_when_missing(self):
        assert ensure_pdf_name("graded-copy") == "graded-copy.pdf"

    def test_case_insensitive_extension_check(self):
        result = ensure_pdf_name("GRADED-COPY.PDF")
        assert result.lower().endswith(".pdf")

    def test_sanitizes_invalid_chars(self):
        result = ensure_pdf_name("file<name>.pdf")
        assert "<" not in result
        assert ">" not in result

    def test_fallback_for_empty_name(self):
        result = ensure_pdf_name("")
        assert result.lower().endswith(".pdf")


class TestExpandCandidateUrls:
    def test_deduplicates_identical_urls(self):
        urls = ["https://example.com/a.pdf", "https://example.com/a.pdf"]
        result = expand_candidate_urls(urls, "https://example.com")
        assert result.count("https://example.com/a.pdf") == 1

    def test_pdf_urls_come_before_non_pdf(self):
        urls = [
            "https://example.com/page",
            "https://example.com/document.pdf",
        ]
        result = expand_candidate_urls(urls, "https://example.com")
        pdf_index = next(i for i, u in enumerate(result) if u.endswith(".pdf"))
        non_pdf_index = next(i for i, u in enumerate(result) if not u.endswith(".pdf"))
        assert pdf_index < non_pdf_index

    def test_relative_urls_resolved_against_base(self):
        urls = ["/courses/1/assignments/2/download.pdf"]
        result = expand_candidate_urls(urls, "https://example.com")
        assert "https://example.com/courses/1/assignments/2/download.pdf" in result

    def test_extracts_nested_url_from_query_param(self):
        nested = "https://example.com/real.pdf"
        url = f"https://example.com/redirect?url={quote(nested)}"
        result = expand_candidate_urls([url], "https://example.com")
        assert nested in result

    def test_empty_input_returns_empty_list(self):
        result = expand_candidate_urls([], "https://example.com")
        assert result == []

    def test_absolute_url_preserved(self):
        url = "https://example.com/path/to/file.pdf"
        result = expand_candidate_urls([url], "https://example.com")
        assert url in result
