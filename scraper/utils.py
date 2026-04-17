from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import parse_qs, unquote, urljoin, urlparse


INVALID_COMPONENT_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1F]')
WHITESPACE = re.compile(r"\s+")
FILENAME_FROM_TEXT = re.compile(r"([A-Za-z0-9._-]+\.[A-Za-z0-9]{1,8})")


def sanitize_component(value: str, fallback: str) -> str:
    cleaned = INVALID_COMPONENT_CHARS.sub("_", value).strip()
    cleaned = WHITESPACE.sub(" ", cleaned).strip(" .")
    return cleaned or fallback


def ensure_directory(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)


def absolute_url(base_url: str, href: str) -> str:
    return urljoin(base_url, href)


def guess_filename(download_url: str, link_text: str, fallback: str = "artifact.bin") -> str:
    parsed = urlparse(download_url)
    basename = Path(unquote(parsed.path)).name
    if basename and "." in basename:
        return sanitize_component(basename, fallback)

    query = parse_qs(parsed.query)
    for key in ("filename", "file", "name"):
        if key in query and query[key]:
            candidate = query[key][0]
            if candidate and "." in candidate:
                return sanitize_component(candidate, fallback)

    match = FILENAME_FROM_TEXT.search(link_text)
    if match:
        return sanitize_component(match.group(1), fallback)

    return fallback


def derive_attempt_label(page_url: str) -> str:
    match = re.search(r"/submissions/(\d+)", page_url)
    if match:
        return f"submission-{match.group(1)}"
    return "assignment-page"


def next_available_path(path: Path) -> Path:
    if not path.exists():
        return path

    stem = path.stem
    suffix = path.suffix
    index = 2
    while True:
        candidate = path.with_name(f"{stem}__{index}{suffix}")
        if not candidate.exists():
            return candidate
        index += 1
