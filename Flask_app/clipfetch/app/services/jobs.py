"""Lightweight in-memory job model on a bounded thread pool.

State lives in this process only, which is why the app runs as ONE Gunicorn process with
threads. Scaling to several processes would require a shared store (e.g. SQLite/Redis).
"""
from __future__ import annotations

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path

from ..config import Config
from ..errors import (AppError, FileExpired, JobNotFound, JobNotReady, ServerBusy, StorageError)
from ..utils.helpers import directory_size, new_job_id, safe_rmtree, truncate
from ..utils.logging import log_event
from .cleanup import ensure_disk_space
from .validation import ValidatedURL

logger = logging.getLogger("clipfetch.jobs")


class JobStatus(str, Enum):
    QUEUED = "queued"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class Job:
    target: ValidatedURL
    preset: str
    id: str = field(default_factory=new_job_id)
    status: JobStatus = JobStatus.QUEUED
    stage: str = "queued"
    progress: float | None = 0.0
    created_at: float = field(default_factory=time.time)
    completed_at: float | None = None
    file_path: Path | None = None
    file_name: str | None = None
    file_size: int | None = None
    error: dict | None = None


class JobManager:
    def __init__(self, config: Config, downloader):
        self._config, self._downloader = config, downloader
        self._jobs: dict[str, Job] = {}
        self._lock = threading.RLock()
        self._executor = ThreadPoolExecutor(max_workers=config.max_concurrent_jobs,
                                            thread_name_prefix="job")

    # --- API used by routes -----------------------------------------------------------
    def submit(self, target: ValidatedURL, preset: str) -> Job:
        with self._lock:
            active = sum(j.status in (JobStatus.QUEUED, JobStatus.PROCESSING) for j in self._jobs.values())
            if active >= self._config.max_concurrent_jobs + self._config.max_queue_size:
                raise ServerBusy(f"{active} active jobs")
            self._check_total_storage_cap()
            job = Job(target=target, preset=preset)
            self._jobs[job.id] = job
        self._executor.submit(self._run, job.id)
        return job

    def _check_total_storage_cap(self) -> None:
        """Hard, deployer-set ceiling on total bytes across downloads/+temp/, independent
        of the OS's actual free disk space (see MAX_TOTAL_STORAGE_MB) -- this is what keeps
        a paid/limited disk from filling up with finished files under real traffic, rather
        than relying solely on the TTL sweep eventually catching up."""
        cfg = self._config
        used = directory_size(cfg.download_dir) + directory_size(cfg.temp_dir)
        if used + cfg.max_file_size_bytes > cfg.max_total_storage_bytes:
            raise StorageError(f"total storage {used} + next file could exceed cap "
                              f"{cfg.max_total_storage_bytes}",
                              user_message="The server's storage is currently full of other "
                                          "people's downloads. Please try again in a few minutes.")

    def get(self, job_id: str) -> Job:
        with self._lock:
            job = self._jobs.get(job_id)
        if job is None:
            raise JobNotFound(job_id)
        return job

    def snapshot(self, job: Job) -> dict:
        with self._lock:
            data = {"job_id": job.id, "status": job.status.value, "stage": job.stage,
                    "progress": job.progress, "error": job.error}
            if job.status is JobStatus.COMPLETED:
                data.update(file_name=job.file_name, file_size=job.file_size,
                            expires_in=max(0, int(job.completed_at + self._config.file_ttl_seconds - time.time())))
            return data

    def file_for(self, job_id: str) -> tuple[Path, str]:
        job = self.get(job_id)
        with self._lock:
            if job.status is JobStatus.COMPLETED and job.file_path and job.file_path.is_file():
                return job.file_path, job.file_name or job.file_path.name
            if job.error and job.error.get("code") == FileExpired.code:
                raise FileExpired(job_id)
            if job.status in (JobStatus.QUEUED, JobStatus.PROCESSING):
                raise JobNotReady(job_id)
        raise JobNotFound(job_id)

    def active_count(self) -> int:
        with self._lock:
            return sum(j.status in (JobStatus.QUEUED, JobStatus.PROCESSING) for j in self._jobs.values())

    def tracked_ids(self) -> set[str]:
        with self._lock:
            return set(self._jobs)

    def expire(self, now: float | None = None) -> None:
        """Delete files of completed jobs past their TTL and forget old job records."""
        now = time.time() if now is None else now
        cfg = self._config
        with self._lock:
            for job in list(self._jobs.values()):
                if job.completed_at is None:
                    continue
                age = now - job.completed_at
                if job.status is JobStatus.COMPLETED and age > cfg.file_ttl_seconds:
                    safe_rmtree(cfg.download_dir / job.id)
                    job.status, job.file_path, job.stage = JobStatus.FAILED, None, "expired"
                    job.error = FileExpired().to_dict()
                if job.status is JobStatus.FAILED and age > cfg.job_record_ttl_seconds:
                    safe_rmtree(cfg.download_dir / job.id)
                    del self._jobs[job.id]

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False, cancel_futures=True)

    # --- worker -----------------------------------------------------------------------
    def _update(self, job: Job, **changes) -> None:
        with self._lock:
            for key, value in changes.items():
                setattr(job, key, value)

    def _run(self, job_id: str) -> None:
        job = self.get(job_id)
        cfg, started = self._config, time.monotonic()
        job_dir = cfg.temp_dir / job.id
        self._update(job, status=JobStatus.PROCESSING, stage="starting")

        def on_progress(pct: float | None, stage: str) -> None:
            self._update(job, progress=pct, stage=stage)

        try:
            ensure_disk_space(cfg.temp_dir, cfg.min_free_disk_bytes, cfg.max_file_size_bytes)
            result = self._downloader.download(job.target, job.preset, job_dir, on_progress)
            dest_dir = cfg.download_dir / job.id
            dest_dir.mkdir(parents=True, exist_ok=True)
            dest = dest_dir / f"media{result.path.suffix}"
            result.path.replace(dest) if result.path.parent.stat().st_dev == dest_dir.stat().st_dev \
                else __import__("shutil").move(str(result.path), str(dest))
            self._update(job, status=JobStatus.COMPLETED, stage="done", progress=100.0,
                         file_path=dest, file_name=result.file_name, file_size=result.size,
                         completed_at=time.time())
            outcome, category, level = "success", None, logging.INFO
        except AppError as exc:
            self._fail(job, exc)
            outcome, category, level = "failed", exc.code, logging.WARNING
            logger.warning("job failed: %s", truncate(exc.detail), extra={"job_id": job.id})
        except Exception:  # noqa: BLE001 - never leak internals; details go to the log
            logger.exception("unexpected job error", extra={"job_id": job.id})
            from ..errors import AppError as _Base
            self._fail(job, _Base())
            outcome, category, level = "failed", "internal_error", logging.ERROR
        finally:
            self._downloader.cleanup(job_dir)
        log_event(logger, level, "job finished", job_id=job.id, platform=job.target.platform,
                  operation="download", duration_ms=int((time.monotonic() - started) * 1000),
                  result=outcome, error_category=category)

    def _fail(self, job: Job, error: AppError) -> None:
        self._update(job, status=JobStatus.FAILED, stage="failed", error=error.to_dict(),
                     completed_at=time.time())
        safe_rmtree(self._config.download_dir / job.id)
