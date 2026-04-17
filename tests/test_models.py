from __future__ import annotations

from scraper.models import Assignment, Course, FileLink, RunSummary


class TestCourse:
    def test_fields(self):
        course = Course(id="1", name="Math 101", url="https://example.com/courses/1")
        assert course.id == "1"
        assert course.name == "Math 101"
        assert course.url == "https://example.com/courses/1"


class TestAssignment:
    def test_fields_and_default_submission_urls(self):
        assignment = Assignment(
            id="10",
            course_id="1",
            title="HW1",
            url="https://example.com/courses/1/assignments/10",
        )
        assert assignment.id == "10"
        assert assignment.course_id == "1"
        assert assignment.title == "HW1"
        assert assignment.submission_urls == []

    def test_submission_urls_are_independent_per_instance(self):
        a1 = Assignment(id="1", course_id="1", title="A1", url="url1")
        a2 = Assignment(id="2", course_id="1", title="A2", url="url2")
        a1.submission_urls.append("x")
        assert a2.submission_urls == []


class TestFileLink:
    def test_fields(self):
        course = Course(id="1", name="Math", url="url")
        assignment = Assignment(id="10", course_id="1", title="HW", url="url")
        link = FileLink(
            course=course,
            assignment=assignment,
            source_page_url="https://example.com/submission",
            download_url="https://example.com/download.pdf",
            attempt_label="submission-1",
            kind="graded_copy",
            suggested_name="graded-copy.pdf",
        )
        assert link.course is course
        assert link.assignment is assignment
        assert link.kind == "graded_copy"
        assert link.suggested_name == "graded-copy.pdf"


class TestRunSummary:
    def test_default_values(self):
        s = RunSummary()
        assert s.courses == 0
        assert s.assignments == 0
        assert s.discovered_links == 0
        assert s.downloaded == 0
        assert s.skipped == 0
        assert s.failed == 0

    def test_custom_values(self):
        s = RunSummary(courses=2, assignments=5, downloaded=3, skipped=1, failed=0, discovered_links=4)
        assert s.courses == 2
        assert s.assignments == 5
        assert s.downloaded == 3
        assert s.skipped == 1
        assert s.discovered_links == 4
