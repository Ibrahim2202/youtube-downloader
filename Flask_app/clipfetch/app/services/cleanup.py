"""Disk-space guard and lifecycle cleanup of temporary/finished job directories."""
from __future__ import annotations

import logging
import shutil
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING

from ..config import Config
from ..errors import StorageError
from ..utils.helpers import is_valid_job_id, safe_rmtree

if TYPE_CHECKING:
    from .jobs import JobManager

logger = logging.getLogger("clipfetch.cleanup")
CACHE_DIR_NAME = "_cache"


def ensure_disk_space(path: Path, min_free_bytes: int, required_bytes: int = 0) -> None:
    try:
        free = shutil.disk_usage(path).free
    except OSError as exc:
        raise StorageError(f"cannot stat disk at {path}: {exc}") from exc
    if free < min_free_bytes + required_bytes:
        raise StorageError(f"free disk {free} < required {min_free_bytes + required_bytes}")


def wipe_directory(root: Path) -> int:
    """Delete everything under `root` except the yt-dlp cache. Used at startup: after a
    restart, in-memory job state is gone, so any leftover files are orphans."""
    removed = 0
    for child in root.iterdir():
        if child.name in {CACHE_DIR_NAME, ".gitkeep"}:
            continue
        if child.is_dir():
            safe_rmtree(child)
        else:
            child.unlink(missing_ok=True)
        removed += 1
    return removed


def sweep_orphans(root: Path, tracked: set[str], older_than: float, now: float | None = None) -> int:
    """Remove job-shaped directories nobody is tracking and that haven't been touched recently."""
    now = time.time() if now is None else now
    removed = 0
    for child in root.iterdir():
        if not (child.is_dir() and is_valid_job_id(child.name)) or child.name in tracked:
            continue
        try:
            if now - child.stat().st_mtime > older_than:
                safe_rmtree(child)
                removed += 1
        except OSError:
            continue
    return removed


class CleanupService:
    """Periodic background sweep. Daemon thread; safe to skip in tests (call run_once)."""

    def __init__(self, config: Config, jobs: "JobManager"):
        self._config, self._jobs = config, jobs
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def run_once(self) -> None:
        self._jobs.expire()
        grace = max(self._config.file_ttl_seconds, self._config.download_timeout) + 60
        tracked = self._jobs.tracked_ids()
        for root in (self._config.temp_dir, self._config.download_dir):
            sweep_orphans(root, tracked, grace)

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, name="cleanup", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _loop(self) -> None:
        while not self._stop.wait(self._config.cleanup_interval):
            try:
                self.run_once()
            except Exception:  # noqa: BLE001 - the sweeper must never die
                logger.exception("cleanup sweep failed")
