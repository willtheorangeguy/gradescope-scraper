from __future__ import annotations

from dataclasses import replace
import hashlib
import re
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, unquote, urlparse

from playwright.sync_api import Error, Locator, Page, sync_playwright

from scraper.config import ScraperConfig
from scraper.manifest import Manifest
from scraper.models import Assignment, Course, FileLink, RunSummary
from scraper.utils import (
    absolute_url,
    derive_attempt_label,
    ensure_directory,
    guess_filename,
    next_available_path,
    sanitize_component,
)

GRADED_COPY_CONTROL_TEXT = re.compile(r"download\s+graded\s+copy", re.IGNORECASE)
PDF_URL_HINT = re.compile(r"\.pdf(?:$|[?#])", re.IGNORECASE)
ASSIGNMENT_ID_REGEX_TEMPLATE = r"/courses/{course_id}/assignments/(\d+)"
SUBMISSION_ID_REGEX_TEMPLATE = r"/courses/{course_id}/assignments/{assignment_id}/submissions/(\d+)"


def run_scraper(config: ScraperConfig) -> RunSummary:
    ensure_directory(config.output_dir)
    ensure_directory(config.state_path.parent)
    manifest = Manifest(config.manifest_path, config.output_dir)
    summary = RunSummary()

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=config.headless)
        try:
            storage_state = str(config.state_path) if config.state_path.exists() else None
            context = browser.new_context(storage_state=storage_state)
            page = context.new_page()

            authenticate(page, context, config)
            if config.login_only:
                return summary

            courses = discover_courses(page, config)
            summary.courses = len(courses)

            assignment_counts: dict[str, int] = {}
            for course in courses:
                assignments = discover_assignments(page, course, config.base_url)
                assignment_counts[course.id] = len(assignments)
                summary.assignments += len(assignments)
                for assignment in assignments:
                    assignment = replace(
                        assignment,
                        submission_urls=discover_submission_pages(page, assignment, config.base_url),
                    )
                    for submission_url in assignment.submission_urls:
                        file_link = FileLink(
                            course=course,
                            assignment=assignment,
                            source_page_url=submission_url,
                            download_url=submission_url,
                            attempt_label=derive_attempt_label(submission_url),
                            kind="graded_copy",
                            suggested_name="graded-copy.pdf",
                        )
                        key = manifest.key_for(file_link)
                        if not config.force and manifest.should_skip_download(key):
                            summary.skipped += 1
                            continue
                        try:
                            downloaded_item, file_path, sha256, size_bytes = download_graded_copy_pdf(
                                page=page,
                                item=file_link,
                                output_dir=config.output_dir,
                                force=config.force,
                                max_retries=config.max_retries,
                                timeout_ms=config.timeout_ms,
                            )
                        except GradedCopyNotFoundError:
                            continue
                        except RuntimeError as exc:
                            summary.failed += 1
                            print(f"Failed to download graded copy from {file_link.source_page_url}: {exc}")
                            continue
                        else:
                            summary.discovered_links += 1
                            manifest.record_download(
                                key=key,
                                item=downloaded_item,
                                file_path=file_path,
                                sha256=sha256,
                                size_bytes=size_bytes,
                            )
                            summary.downloaded += 1
                            manifest.save()

            manifest.record_discovery(courses, assignment_counts)
            manifest.save()
            return summary
        finally:
            browser.close()


def authenticate(page: Page, context: Any, config: ScraperConfig) -> None:
    account_url = absolute_url(config.base_url, "/account")
    login_url = absolute_url(config.base_url, "/login")
    page.goto(account_url, wait_until="domcontentloaded", timeout=config.timeout_ms)
    if is_login_page(page):
        page.goto(login_url, wait_until="domcontentloaded", timeout=config.timeout_ms)
        print("Sign in to Gradescope in the opened browser window.")
        input("After completing login (including 2FA), press Enter to continue...")
        page.goto(account_url, wait_until="domcontentloaded", timeout=config.timeout_ms)
        if is_login_page(page):
            raise RuntimeError("Login did not complete. Still on login page after manual sign-in.")
    context.storage_state(path=str(config.state_path))
    print(f"Saved authenticated session to: {config.state_path}")


def is_login_page(page: Page) -> bool:
    current_url = page.url.lower()
    if "/login" in current_url:
        return True
    login_form = page.locator("form[action*='login']")
    email_field = page.locator("input[name='email']")
    return login_form.count() > 0 or email_field.count() > 0


def discover_courses(page: Page, config: ScraperConfig) -> list[Course]:
    page.goto(absolute_url(config.base_url, "/account"), wait_until="domcontentloaded", timeout=config.timeout_ms)
    raw_ids = page.evaluate(
        """
        () => {
          const ids = new Set();
          for (const anchor of document.querySelectorAll("a[href]")) {
            const href = anchor.getAttribute("href") || "";
            const match = href.match(/\\/courses\\/(\\d+)/);
            if (match) ids.add(match[1]);
          }
          return Array.from(ids);
        }
        """
    )
    if not isinstance(raw_ids, list):
        raise RuntimeError("Could not discover courses from account page.")

    selected_ids = [str(value) for value in raw_ids]
    if config.course_ids:
        allow = set(config.course_ids)
        selected_ids = [course_id for course_id in selected_ids if course_id in allow]

    courses: list[Course] = []
    for course_id in selected_ids:
        course_url = absolute_url(config.base_url, f"/courses/{course_id}")
        page.goto(course_url, wait_until="domcontentloaded", timeout=config.timeout_ms)
        name = page.evaluate(
            """
            () => {
              const selectors = [
                "h1.courseHeader--title",
                "h1.courseHeader--titleText",
                "h1",
                ".courseHeader--title",
                ".courseHeader--titleText"
              ];
              for (const selector of selectors) {
                const node = document.querySelector(selector);
                if (node && node.textContent && node.textContent.trim()) {
                  return node.textContent.trim();
                }
              }
              return document.title || "Unnamed course";
            }
            """
        )
        course_name = str(name) if isinstance(name, str) else f"course-{course_id}"
        courses.append(Course(id=course_id, name=course_name, url=course_url))

    print(f"Discovered {len(courses)} course(s).")
    return courses


def discover_assignments(page: Page, course: Course, base_url: str) -> list[Assignment]:
    page.goto(course.url, wait_until="domcontentloaded")
    regex_source = ASSIGNMENT_ID_REGEX_TEMPLATE.format(course_id=re.escape(course.id))
    raw_assignments = page.evaluate(
        """
        (pattern) => {
          const regex = new RegExp(pattern);
          const seen = new Set();
          const items = [];
          for (const anchor of document.querySelectorAll("a[href]")) {
            const href = anchor.getAttribute("href") || "";
            const match = href.match(regex);
            if (!match) continue;
            const assignmentId = match[1];
            if (seen.has(assignmentId)) continue;
            seen.add(assignmentId);
            const title = (anchor.textContent || "").trim() || `assignment-${assignmentId}`;
            items.push({
              id: assignmentId,
              title,
              href
            });
          }
          return items;
        }
        """,
        regex_source,
    )
    if not isinstance(raw_assignments, list):
        raise RuntimeError(f"Could not discover assignments for course {course.id}.")

    assignments: list[Assignment] = []
    for entry in raw_assignments:
        if not isinstance(entry, dict):
            continue
        assignment_id = str(entry.get("id", "")).strip()
        if not assignment_id:
            continue
        title = str(entry.get("title", "")).strip() or f"assignment-{assignment_id}"
        url = absolute_url(base_url, f"/courses/{course.id}/assignments/{assignment_id}")
        assignments.append(Assignment(id=assignment_id, course_id=course.id, title=title, url=url))

    print(f"[{course.name}] Discovered {len(assignments)} assignment(s).")
    return assignments


def discover_submission_pages(page: Page, assignment: Assignment, base_url: str) -> list[str]:
    page.goto(assignment.url, wait_until="domcontentloaded")
    regex_source = SUBMISSION_ID_REGEX_TEMPLATE.format(
        course_id=re.escape(assignment.course_id),
        assignment_id=re.escape(assignment.id),
    )
    raw_urls = page.evaluate(
        """
        (pattern) => {
          const regex = new RegExp(pattern);
          const urls = new Set();
          for (const anchor of document.querySelectorAll("a[href]")) {
            const href = anchor.getAttribute("href") || "";
            if (regex.test(href)) urls.add(href);
          }
          return Array.from(urls);
        }
        """,
        regex_source,
    )
    if not isinstance(raw_urls, list):
        return [assignment.url]

    targets = [assignment.url]
    for href in raw_urls:
        if isinstance(href, str) and href.strip():
            targets.append(absolute_url(base_url, href))
    deduplicated = sorted(set(targets))
    return deduplicated


class GradedCopyNotFoundError(RuntimeError):
    """Raised when a submission page has no 'Download Graded Copy' control."""


def find_graded_copy_control(page: Page) -> Locator | None:
    selectors = (
        page.get_by_role("button", name=GRADED_COPY_CONTROL_TEXT),
        page.get_by_role("link", name=GRADED_COPY_CONTROL_TEXT),
        page.locator("button:has-text('Download Graded Copy')"),
        page.locator("a:has-text('Download Graded Copy')"),
    )
    for locator in selectors:
        count = locator.count()
        if count == 0:
            continue
        for index in range(count):
            candidate = locator.nth(index)
            if candidate.is_visible():
                return candidate
        return locator.first
    return None


def ensure_pdf_name(name: str) -> str:
    normalized = sanitize_component(name, "graded-copy.pdf")
    if normalized.lower().endswith(".pdf"):
        return normalized
    return f"{normalized}.pdf"


def extract_control_urls(control: Locator, base_url: str) -> list[str]:
    urls: list[str] = []
    for attribute in ("href", "data-href", "data-url"):
        value = control.get_attribute(attribute)
        if value and value.strip():
            urls.append(absolute_url(base_url, value.strip()))
    return urls


def extract_urls_from_page(page: Page) -> list[str]:
    try:
        raw_urls = page.evaluate(
            """
            () => {
              const urls = [];
              for (const attr of ["href", "src", "data"]) {
                for (const node of document.querySelectorAll(`[${attr}]`)) {
                  const value = node.getAttribute(attr);
                  if (value) urls.push(value);
                }
              }
              urls.push(window.location.href);
              return urls;
            }
            """
        )
    except Error:
        return []

    if not isinstance(raw_urls, list):
        return []
    extracted: list[str] = []
    for value in raw_urls:
        if isinstance(value, str) and value.strip():
            extracted.append(value.strip())
    return extracted


def expand_candidate_urls(urls: list[str], base_url: str) -> list[str]:
    expanded: set[str] = set()
    for raw_url in urls:
        absolute = absolute_url(base_url, raw_url)
        expanded.add(absolute)
        parsed = urlparse(absolute)
        for values in parse_qs(parsed.query).values():
            for value in values:
                decoded = unquote(value).strip()
                if not decoded:
                    continue
                if decoded.startswith(("http://", "https://", "/")):
                    expanded.add(absolute_url(base_url, decoded))

    prioritized = sorted(expanded, key=lambda url: (0 if PDF_URL_HINT.search(url) else 1, url))
    return prioritized


def try_fetch_pdf_from_urls(page: Page, urls: list[str], timeout_ms: int) -> tuple[str, bytes] | None:
    for candidate_url in urls:
        try:
            response = page.context.request.get(candidate_url, timeout=timeout_ms)
        except Error:
            continue
        if not response.ok:
            continue
        body = response.body()
        if not body:
            continue
        content_type = ""
        for key, value in response.headers.items():
            if key.lower() == "content-type":
                content_type = value.lower()
                break
        if body.startswith(b"%PDF-") or "application/pdf" in content_type:
            return candidate_url, body
    return None


def persist_pdf_bytes(target_dir: Path, file_name: str, body: bytes, force: bool) -> tuple[Path, str, int]:
    target_path = target_dir / ensure_pdf_name(file_name)
    if target_path.exists() and not force:
        target_path = next_available_path(target_path)
    target_path.write_bytes(body)
    sha256 = hashlib.sha256(body).hexdigest()
    return target_path, sha256, len(body)


def download_graded_copy_pdf(
    *,
    page: Page,
    item: FileLink,
    output_dir: Path,
    force: bool,
    max_retries: int,
    timeout_ms: int,
) -> tuple[FileLink, Path, str, int]:
    course_part = sanitize_component(item.course.name, f"course-{item.course.id}")
    assignment_part = sanitize_component(item.assignment.title, f"assignment-{item.assignment.id}")
    attempt_part = sanitize_component(item.attempt_label, "attempt")
    target_dir = output_dir / course_part / assignment_part / attempt_part
    ensure_directory(target_dir)

    last_error: Exception | None = None
    for attempt in range(1, max_retries + 1):
        attempt_timeout = timeout_ms * attempt
        try:
            page.goto(item.source_page_url, wait_until="domcontentloaded", timeout=attempt_timeout)
            control = find_graded_copy_control(page)
            if control is None:
                raise GradedCopyNotFoundError(f"No 'Download Graded Copy' control on {item.source_page_url}")

            pre_click_urls = expand_candidate_urls(extract_control_urls(control, item.source_page_url), item.source_page_url)
            pre_click_pdf = try_fetch_pdf_from_urls(page, pre_click_urls, attempt_timeout)
            if pre_click_pdf is not None:
                pdf_url, body = pre_click_pdf
                file_name = guess_filename(pdf_url, item.suggested_name, fallback=item.suggested_name)
                target_path, sha256, size_bytes = persist_pdf_bytes(target_dir, file_name, body, force)
                downloaded_item = replace(item, download_url=pdf_url, suggested_name=target_path.name)
                return downloaded_item, target_path, sha256, size_bytes

            existing_pages = list(page.context.pages)
            try:
                with page.expect_download(timeout=attempt_timeout) as download_info:
                    control.click(timeout=attempt_timeout)
                download = download_info.value
                failure = download.failure()
                if failure:
                    raise RuntimeError(f"Browser reported a failed download: {failure}")

                name = ensure_pdf_name(download.suggested_filename or item.suggested_name)
                target_path = target_dir / name
                if target_path.exists() and not force:
                    target_path = next_available_path(target_path)

                download.save_as(str(target_path))
                body = target_path.read_bytes()
                if not body:
                    raise RuntimeError(f"Downloaded empty file from {item.source_page_url}")

                sha256 = hashlib.sha256(body).hexdigest()
                downloaded_item = replace(item, suggested_name=target_path.name)
                return downloaded_item, target_path, sha256, len(body)
            except Error:
                page.wait_for_timeout(1000)
                runtime_urls = [page.url]
                runtime_urls.extend(extract_urls_from_page(page))

                for popup in page.context.pages:
                    if popup in existing_pages:
                        continue
                    try:
                        popup.wait_for_load_state("domcontentloaded", timeout=attempt_timeout)
                    except Error:
                        pass
                    runtime_urls.append(popup.url)
                    runtime_urls.extend(extract_urls_from_page(popup))
                    try:
                        popup.close()
                    except Error:
                        pass

                candidate_urls = expand_candidate_urls(runtime_urls, item.source_page_url)
                fetched_pdf = try_fetch_pdf_from_urls(page, candidate_urls, attempt_timeout)
                if fetched_pdf is None:
                    raise RuntimeError("Clicked graded-copy control but could not resolve a downloadable PDF URL.")

                pdf_url, body = fetched_pdf
                file_name = guess_filename(pdf_url, item.suggested_name, fallback=item.suggested_name)
                target_path, sha256, size_bytes = persist_pdf_bytes(target_dir, file_name, body, force)
                downloaded_item = replace(item, download_url=pdf_url, suggested_name=target_path.name)
                return downloaded_item, target_path, sha256, size_bytes
        except GradedCopyNotFoundError:
            raise
        except (Error, RuntimeError) as exc:
            last_error = exc
            if attempt < max_retries:
                continue
            raise RuntimeError(
                f"Failed to download graded copy from {item.source_page_url} "
                f"after {max_retries} attempts (timeout={attempt_timeout}ms): {exc}"
            ) from exc

    if last_error is not None:
        raise RuntimeError(f"Failed to download graded copy from {item.source_page_url}: {last_error}") from last_error
    raise RuntimeError(f"Failed to download graded copy from {item.source_page_url}: unknown error")
