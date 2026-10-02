"""Extraction/download engine. Everything yt-dlp-specific lives here.

yt-dlp runs as a subprocess (argument list, scrubbed environment, own process group) so a
hung extractor or FFmpeg merge can be killed on timeout. The rest of the app only sees
`DownloaderService`, so the engine can be upgraded or swapped independently.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import signal
import subprocess
import sys
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from ..config import Config
from ..errors import (DownloadTimeout, ExtractionError, FFmpegError, FileTooLarge,
                      classify_ytdlp_failure)
from ..utils.helpers import safe_rmtree, sanitize_filename
from .ffmpeg import FFmpegInfo
from .media_info import MediaInfo, parse_media_info
from .validation import ValidatedURL, validate_url

logger = logging.getLogger("clipfetch.downloader")

PROGRESS_PREFIX = "CFPROGRESS"
_PROGRESS_TEMPLATE = (f"download:{PROGRESS_PREFIX} %(progress.downloaded_bytes)s "
                      "%(progress.total_bytes)s %(progress.total_bytes_estimate)s")
_PROCESSING_MARKERS = ("[Merger]", "[ExtractAudio]", "[VideoConvertor]", "[VideoRemuxer]", "[Fixup")
_IGNORED_SUFFIXES = (".part", ".ytdl", ".temp", ".info.json")

ProgressCallback = Callable[[float | None, str], None]


@dataclass(frozen=True)
class DownloadResult:
    path: Path
    file_name: str
    size: int
    title: str


def build_format_args(preset: str, ffmpeg_available: bool) -> list[str]:
    """Map a server-defined preset ID to yt-dlp arguments. `preset` must already be validated."""
    if preset == "audio":
        if ffmpeg_available:
            return ["-f", "ba/b", "-x", "--audio-format", "mp3", "--audio-quality", "192K"]
        return ["-f", "ba[ext=m4a]/ba/b"]
    height = int(preset[1:])
    if ffmpeg_available:
        return ["-f", f"bv*[height<=?{height}]+ba/b[height<=?{height}]",
                "-S", "res,ext:mp4:m4a", "--merge-output-format", "mp4"]
    return ["-f", f"b[height<=?{height}]/b"]


def _kill(proc: subprocess.Popen) -> None:
    try:
        if os.name == "posix":
            os.killpg(proc.pid, signal.SIGKILL)
        else:
            proc.kill()
    except (ProcessLookupError, PermissionError, OSError):
        pass


class DownloaderService:
    def __init__(self, config: Config, ffmpeg: FFmpegInfo | None):
        self._config = config
        self._ffmpeg = ffmpeg
        self._cache_dir = config.temp_dir / "_cache"

    @property
    def ffmpeg_available(self) -> bool:
        return self._ffmpeg is not None

    # --- public interface -------------------------------------------------------------
    def validate_url(self, raw: object) -> ValidatedURL:
        return validate_url(raw)

    def extract_info(self, target: ValidatedURL) -> MediaInfo:
        cmd = self._base_args() + ["--dump-single-json", "--skip-download", "--", target.url]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                                  errors="replace", timeout=self._config.info_timeout,
                                  check=False, stdin=subprocess.DEVNULL, env=self._child_env())
        except subprocess.TimeoutExpired:
            raise DownloadTimeout("metadata lookup timed out") from None
        except OSError as exc:
            raise ExtractionError(f"could not start yt-dlp: {exc}") from exc
        if proc.returncode != 0:
            raise classify_ytdlp_failure(proc.stderr, target.platform)
        try:
            raw = json.loads(proc.stdout)
        except ValueError:
            raise ExtractionError("yt-dlp returned invalid JSON") from None
        if not isinstance(raw, dict):
            raise ExtractionError("yt-dlp returned unexpected metadata")
        return parse_media_info(raw, platform=target.platform, config=self._config,
                                ffmpeg_available=self.ffmpeg_available)

    def download(self, target: ValidatedURL, preset: str, job_dir: Path,
                 on_progress: ProgressCallback) -> DownloadResult:
        cfg = self._config
        job_dir.mkdir(parents=True, exist_ok=True)
        out_template = str(job_dir).replace("%", "%%") + os.sep + "media.%(ext)s"
        cmd = (self._base_args()
               + ["--newline", "--progress-template", _PROGRESS_TEMPLATE, "--write-info-json",
                  "--no-mtime", "-o", out_template,
                  "--max-filesize", str(cfg.max_file_size_bytes),
                  "--match-filters", f"!is_live & duration <=? {cfg.max_duration_seconds}"]
               + build_format_args(preset, self.ffmpeg_available)
               + ["--", target.url])

        flags = {"timeout": False, "oversize": False}
        tail: deque[str] = deque(maxlen=60)
        try:
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, text=True, encoding="utf-8",
                                    errors="replace", env=self._child_env(),
                                    start_new_session=(os.name == "posix"))
        except OSError as exc:
            raise ExtractionError(f"could not start yt-dlp: {exc}") from exc

        def on_timeout() -> None:
            flags["timeout"] = True
            _kill(proc)

        watchdog = threading.Timer(cfg.download_timeout, on_timeout)
        watchdog.daemon = True
        watchdog.start()
        try:
            for line in proc.stdout:  # type: ignore[union-attr]
                line = line.rstrip()
                if line.startswith(PROGRESS_PREFIX):
                    self._handle_progress(line, on_progress, flags, proc)
                else:
                    tail.append(line)
                    if line.startswith(_PROCESSING_MARKERS):
                        on_progress(None, "processing")
            proc.wait()
        finally:
            watchdog.cancel()
            if proc.poll() is None:
                _kill(proc)
                proc.wait()

        if flags["timeout"]:
            raise DownloadTimeout("download exceeded DOWNLOAD_TIMEOUT")
        if flags["oversize"]:
            raise FileTooLarge("downloaded bytes exceeded MAX_FILE_SIZE")
        output = "\n".join(tail)
        if proc.returncode != 0:
            raise classify_ytdlp_failure(output, target.platform)
        return self._collect_result(job_dir, output, target.platform)

    def cleanup(self, job_dir: Path) -> None:
        safe_rmtree(job_dir)

    # --- internals --------------------------------------------------------------------
    def _handle_progress(self, line: str, on_progress: ProgressCallback, flags: dict,
                         proc: subprocess.Popen) -> None:
        parts = line.split()[1:]

        def num(i: int) -> float | None:
            try:
                return float(parts[i])
            except (IndexError, ValueError):
                return None

        done, total, estimate = num(0), num(1), num(2)
        if done is not None and done > self._config.max_file_size_bytes:
            flags["oversize"] = True
            _kill(proc)
            return
        size = total or estimate
        on_progress(min(99.0, done / size * 100) if done is not None and size else None, "downloading")

    def _collect_result(self, job_dir: Path, output: str, platform: str) -> DownloadResult:
        candidates = [p for p in job_dir.glob("media.*")
                      if p.is_file() and not p.name.endswith(_IGNORED_SUFFIXES)]
        if not candidates:
            raise classify_ytdlp_failure(output or "no output file produced", platform)
        path = max(candidates, key=lambda p: p.stat().st_size)
        size = path.stat().st_size
        if size > self._config.max_file_size_bytes:
            raise FileTooLarge(f"final file {size} bytes")
        if size == 0:
            raise ExtractionError("output file is empty")
        title = "video"
        info_file = job_dir / "media.info.json"
        try:
            title = str(json.loads(info_file.read_text(encoding="utf-8")).get("title") or "video")
        except (OSError, ValueError):
            pass
        return DownloadResult(path=path, file_name=f"{sanitize_filename(title)}{path.suffix}",
                              size=size, title=title)

    def _base_args(self) -> list[str]:
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        args = [sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist", "--no-warnings",
                "--no-color", "--socket-timeout", "15", "--retries", "3", "--fragment-retries", "3",
                "--cache-dir", str(self._cache_dir)]
        if self._ffmpeg:
            args += ["--ffmpeg-location", self._ffmpeg.path]
        args += list(self._config.extra_ytdlp_args)
        return args

    def _child_env(self) -> dict[str, str]:
        """Minimal environment so server secrets never reach the child process."""
        keep = ("PATH", "SYSTEMROOT", "TEMP", "TMP", "LANG", "LC_ALL", "HOME", "USERPROFILE")
        env = {k: os.environ[k] for k in keep if k in os.environ}
        env.update(PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
        return env
