"""FFmpeg discovery and health check (yt-dlp invokes FFmpeg itself for merging/conversion)."""
from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

from ..errors import FFmpegError


@dataclass(frozen=True)
class FFmpegInfo:
    path: str
    version: str


def locate_ffmpeg(configured: str | None = None) -> str | None:
    if configured:
        found = shutil.which(configured)
        if found:
            return found
        return configured if Path(configured).is_file() else None
    return shutil.which("ffmpeg")


def check_ffmpeg(configured: str | None = None, timeout: int = 10) -> FFmpegInfo:
    """Locate ffmpeg and confirm it runs. Raises FFmpegError with a clear diagnostic."""
    path = locate_ffmpeg(configured)
    if not path:
        where = f"FFMPEG_PATH={configured!r}" if configured else "PATH"
        raise FFmpegError(f"ffmpeg not found via {where}. Install it (e.g. `apt install ffmpeg`) "
                          "or set FFMPEG_PATH.")
    try:
        proc = subprocess.run([path, "-version"], capture_output=True, text=True,
                              timeout=timeout, check=False, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FFmpegError(f"ffmpeg at {path} could not be executed: {exc}") from exc
    if proc.returncode != 0:
        raise FFmpegError(f"ffmpeg at {path} exited with {proc.returncode}: {proc.stderr[-300:]}")
    first_line = (proc.stdout.splitlines() or ["ffmpeg (unknown version)"])[0]
    return FFmpegInfo(path=path, version=first_line)
