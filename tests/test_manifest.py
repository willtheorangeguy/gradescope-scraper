from __future__ import annotations

import json

import pytest

from scraper.manifest import Manifest, utc_now_iso
from scraper.models import Assignment, Course, FileLink


def _make_file_link(
    course_id: str = "1",
    assignment_id: str = "10",
    source_page_url: str = "https://example.com/submission/1",
    download_url: str = "https://example.com/download.pdf",
) -> FileLink:
    course = Course(id=course_id, name="Math 101", url=f"https://example.com/courses/{course_id}")
    assignment = Assignment(id=assignment_id, course_id=course_id, title="HW1", url="https://example.com/")
    return FileLink(
        course=course,
        assignment=assignment,
        source_page_url=source_page_url,
        download_url=download_url,
        attempt_label="submission-1",
        kind="graded_copy",
        suggested_name="graded-copy.pdf",
    )


class TestUtcNowIso:
    def test_returns_iso_string(self):
        result = utc_now_iso()
        assert isinstance(result, str)
        assert "T" in result
        assert result.endswith("+00:00")


class TestManifestInit:
    def test_fresh_manifest_has_correct_structure(self, tmp_path):
        m = Manifest(tmp_path / "manifest.json", tmp_path)
        assert m.data["version"] == 1
        assert "created_at" in m.data
        assert "updated_at" in m.data
        assert m.data["downloaded"] == {}
        assert m.data["discovery"] == {}

    def test_loads_existing_manifest(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        existing = {
            "version": 1,
            "created_at": "2024-01-01T00:00:00+00:00",
            "updated_at": "2024-01-01T00:00:00+00:00",
            "downloaded": {"abc": {"path": "some/file.pdf"}},
            "discovery": {},
        }
        manifest_path.write_text(json.dumps(existing), encoding="utf-8")
        m = Manifest(manifest_path, tmp_path)
        assert m.data["downloaded"]["abc"]["path"] == "some/file.pdf"

    def test_invalid_json_object_raises_value_error(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text("[1, 2, 3]", encoding="utf-8")
        with pytest.raises(ValueError, match="not a JSON object"):
            Manifest(manifest_path, tmp_path)

    def test_creates_parent_directory(self, tmp_path):
        manifest_path = tmp_path / "subdir" / "manifest.json"
        Manifest(manifest_path, tmp_path)
        assert (tmp_path / "subdir").is_dir()

    def test_missing_keys_get_defaults(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        manifest_path.write_text(json.dumps({"version": 1}), encoding="utf-8")
        m = Manifest(manifest_path, tmp_path)
        assert m.data["downloaded"] == {}
        assert m.data["discovery"] == {}


class TestManifestSave:
    def test_save_writes_valid_json(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        m = Manifest(manifest_path, tmp_path)
        m.save()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert data["version"] == 1

    def test_save_updates_updated_at_field(self, tmp_path):
        manifest_path = tmp_path / "manifest.json"
        m = Manifest(manifest_path, tmp_path)
        m.save()
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert "updated_at" in data


class TestManifestKeyFor:
    def test_key_is_deterministic(self, tmp_path):
        m = Manifest(tmp_path / "manifest.json", tmp_path)
        link = _make_file_link()
        assert m.key_for(link) == m.key_for(link)

    def test_different_links_have_different_keys(self, tmp_path):
        m = Manifest(tmp_path / "manifest.json", tmp_path)
        link1 = _make_file_link(source_page_url="https://example.com/submission/1")
        link2 = _make_file_link(source_page_url="https://example.com/submission/2")
        assert m.key_for(link1) != m.key_for(link2)

    def test_key_is_lowercase_hex(self, tmp_path):
        m = Manifest(tmp_path / "manifest.json", tmp_path)
        key = m.key_for(_make_file_link())
        assert all(c in "0123456789abcdef" for c in key)
        assert len(key) == 40  # SHA-1


class TestManifestShouldSkipDownload:
    def test_returns_false_for_unknown_key(self, tmp_path):
        m = Manifest(tmp_path / "manifest.json", tmp_path)
        assert m.should_skip_download("nonexistent") is False

    def test_returns_false_when_recorded_file_is_missing(self, tmp_path):
        m = Manifest(tmp_path / "manifest.json", tmp_path)
        m.data["downloaded"]["abc"] = {"path": "missing/file.pdf"}
        assert m.should_skip_download("abc") is False

    def test_returns_true_when_file_exists_on_disk(self, tmp_path):
        m = Manifest(tmp_path / "manifest.json", tmp_path)
        existing_file = tmp_path / "file.pdf"
        existing_file.write_bytes(b"data")
        m.data["downloaded"]["abc"] = {"path": "file.pdf"}
        assert m.should_skip_download("abc") is True

    def test_returns_false_when_entry_has_no_path(self, tmp_path):
        m = Manifest(tmp_path / "manifest.json", tmp_path)
        m.data["downloaded"]["abc"] = {"sha256": "deadbeef"}
        assert m.should_skip_download("abc") is False


class TestManifestRecordDownload:
    def test_records_entry_with_correct_fields(self, tmp_path):
        m = Manifest(tmp_path / "manifest.json", tmp_path)
        link = _make_file_link()
        file_path = tmp_path / "course" / "hw1" / "graded-copy.pdf"
        file_path.parent.mkdir(parents=True)
        file_path.write_bytes(b"pdf data")
        key = m.key_for(link)
        m.record_download(key=key, item=link, file_path=file_path, sha256="abc123", size_bytes=8)
        entry = m.data["downloaded"][key]
        assert entry["course_id"] == "1"
        assert entry["assignment_id"] == "10"
        assert entry["sha256"] == "abc123"
        assert entry["size_bytes"] == 8
        assert entry["kind"] == "graded_copy"
        assert "downloaded_at" in entry

    def test_path_is_relative_to_output_dir(self, tmp_path):
        m = Manifest(tmp_path / "manifest.json", tmp_path)
        link = _make_file_link()
        file_path = tmp_path / "sub" / "graded-copy.pdf"
        file_path.parent.mkdir(parents=True)
        file_path.write_bytes(b"data")
        key = m.key_for(link)
        m.record_download(key=key, item=link, file_path=file_path, sha256="x", size_bytes=4)
        assert m.data["downloaded"][key]["path"] == "sub/graded-copy.pdf"


class TestManifestRecordDiscovery:
    def test_records_courses_and_counts(self, tmp_path):
        m = Manifest(tmp_path / "manifest.json", tmp_path)
        courses = [
            Course(id="1", name="Math", url="https://example.com/courses/1"),
            Course(id="2", name="Physics", url="https://example.com/courses/2"),
        ]
        m.record_discovery(courses, {"1": 3, "2": 5})
        disc = m.data["discovery"]
        assert len(disc["courses"]) == 2
        assert disc["assignment_counts"] == {"1": 3, "2": 5}
        assert "captured_at" in disc

    def test_courses_serialized_as_dicts(self, tmp_path):
        m = Manifest(tmp_path / "manifest.json", tmp_path)
        courses = [Course(id="1", name="Math", url="https://example.com/courses/1")]
        m.record_discovery(courses, {"1": 2})
        course_data = m.data["discovery"]["courses"][0]
        assert course_data["id"] == "1"
        assert course_data["name"] == "Math"
