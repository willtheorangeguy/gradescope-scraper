from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class ScraperConfig:
    base_url: str
    output_dir: Path
    state_path: Path
    manifest_path: Path
    headless: bool
    force: bool
    login_only: bool
    max_retries: int
    timeout_ms: int
    course_ids: list[str]
