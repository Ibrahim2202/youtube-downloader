"""Small pure helpers."""
from __future__ import annotations

import re
import shutil
import unicodedata
import uuid
from pathlib import Path

_JOB_ID_RE = re.compile(r"^[0-9a-f]{32}$")
_ILLEGAL_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f\x7f]')
_RESERVED_NAMES = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)),
                   *(f"lpt{i}" for i in range(1, 10))}


def new_job_id() -> str:
    return uuid.uuid4().hex


def is_valid_job_id(value: object) -> bool:
    return isinstance(value, str) and bool(_JOB_ID_RE.match(value))


def sanitize_filename(name: str | None, fallback: str = "video", max_length: int = 100) -> str:
    """Return a filesystem-safe display name (no extension). Unicode letters are preserved."""
    text = unicodedata.normalize("NFKC", name or "")
    text = _ILLEGAL_CHARS.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip(" .")
    text = text[:max_length].strip(" .")
    if not text or text.lower() in _RESERVED_NAMES:
        return fallback
    return text


def directory_size(path: Path) -> int:
    """Total size in bytes of every file under `path`, recursively. Never raises: a
    directory that vanishes mid-walk (a job finishing concurrently) just contributes 0 for
    that entry rather than crashing the caller."""
    total = 0
    if not path.is_dir():
        return 0
    for entry in path.rglob("*"):
        try:
            if entry.is_file():
                total += entry.stat().st_size
        except OSError:
            continue
    return total


def safe_rmtree(path: Path) -> None:
    """Remove a directory tree, never raising (cleanup must not mask the real error)."""
    shutil.rmtree(path, ignore_errors=True)


def truncate(text: str | None, limit: int = 500) -> str:
    text = text or ""
    return text if len(text) <= limit else text[:limit] + "…"
