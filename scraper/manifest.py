from __future__ import annotations

from dataclasses import asdict
from datetime import UTC, datetime
import hashlib
import json
from pathlib import Path
from typing import Any

from scraper.models import Course, FileLink
from scraper.utils import ensure_directory


def utc_now_iso() -> str:
    return datetime.now(UTC).isoformat()


class Manifest:
    def __init__(self, path: Path, output_dir: Path) -> None:
        self.path = path
        self.output_dir = output_dir
        ensure_directory(path.parent)
        self.data = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.path.exists():
            return {
                "version": 1,
                "created_at": utc_now_iso(),
                "updated_at": utc_now_iso(),
                "downloaded": {},
                "discovery": {},
            }

        raw = self.path.read_text(encoding="utf-8")
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError(f"Manifest file is not a JSON object: {self.path}")
        parsed.setdefault("downloaded", {})
        parsed.setdefault("discovery", {})
        return parsed

    def save(self) -> None:
        self.data["updated_at"] = utc_now_iso()
        self.path.write_text(json.dumps(self.data, indent=2, sort_keys=True), encoding="utf-8")

    def key_for(self, item: FileLink) -> str:
        digest_source = "|".join(
            [
                item.course.id,
                item.assignment.id,
                item.source_page_url,
                item.download_url,
            ]
        )
        return hashlib.sha1(digest_source.encode("utf-8")).hexdigest()

    def should_skip_download(self, key: str) -> bool:
        entry = self.data["downloaded"].get(key)
        if not isinstance(entry, dict):
            return False
        relative_path = entry.get("path")
        if not isinstance(relative_path, str):
            return False
        return (self.output_dir / relative_path).exists()

    def record_download(
        self,
        *,
        key: str,
        item: FileLink,
        file_path: Path,
        sha256: str,
        size_bytes: int,
    ) -> None:
        relative = file_path.relative_to(self.output_dir).as_posix()
        self.data["downloaded"][key] = {
            "course_id": item.course.id,
            "course_name": item.course.name,
            "assignment_id": item.assignment.id,
            "assignment_title": item.assignment.title,
            "source_page_url": item.source_page_url,
            "download_url": item.download_url,
            "attempt": item.attempt_label,
            "kind": item.kind,
            "path": relative,
            "sha256": sha256,
            "size_bytes": size_bytes,
            "downloaded_at": utc_now_iso(),
        }

    def record_discovery(self, courses: list[Course], assignment_counts: dict[str, int]) -> None:
        serialized = [asdict(course) for course in courses]
        self.data["discovery"] = {
            "captured_at": utc_now_iso(),
            "courses": serialized,
            "assignment_counts": assignment_counts,
        }
