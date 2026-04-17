from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(slots=True)
class Course:
    id: str
    name: str
    url: str


@dataclass(slots=True)
class Assignment:
    id: str
    course_id: str
    title: str
    url: str
    submission_urls: list[str] = field(default_factory=list)


@dataclass(slots=True)
class FileLink:
    course: Course
    assignment: Assignment
    source_page_url: str
    download_url: str
    attempt_label: str
    kind: str
    suggested_name: str


@dataclass(slots=True)
class RunSummary:
    courses: int = 0
    assignments: int = 0
    discovered_links: int = 0
    downloaded: int = 0
    skipped: int = 0
    failed: int = 0
