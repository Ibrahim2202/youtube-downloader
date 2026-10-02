"""Centralised, environment-driven configuration."""
from __future__ import annotations

import os
import secrets
import shlex
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from .errors import ConfigurationError

BASE_DIR = Path(__file__).resolve().parent.parent
_MB = 1024 * 1024


def _get(env: Mapping[str, str], name: str, default: str | None = None) -> str | None:
    value = env.get(name)
    if not value:
        return default
    value = value.strip()
    # Guards against a common .env authoring mistake: `KEY=   # comment` with no real value.
    # python-dotenv only strips inline comments when a real value precedes them, so an
    # empty value followed by a comment is otherwise read back as the literal comment text.
    if not value or value.startswith("#"):
        return default
    return value


def _int(env: Mapping[str, str], name: str, default: int, minimum: int = 1) -> int:
    raw = _get(env, name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError:
        raise ConfigurationError(f"{name} must be an integer, got {raw!r}") from None
    if value < minimum:
        raise ConfigurationError(f"{name} must be >= {minimum}, got {value}")
    return value


def _bool(env: Mapping[str, str], name: str, default: bool) -> bool:
    raw = _get(env, name)
    if raw is None:
        return default
    if raw.lower() in {"1", "true", "yes", "on"}:
        return True
    if raw.lower() in {"0", "false", "no", "off"}:
        return False
    raise ConfigurationError(f"{name} must be true/false, got {raw!r}")


def _path(env: Mapping[str, str], name: str, default: str) -> Path:
    path = Path(_get(env, name, default) or default).expanduser()
    return path if path.is_absolute() else BASE_DIR / path


def _ytdlp_args(env: Mapping[str, str], name: str) -> tuple[str, ...]:
    """Extra raw yt-dlp arguments for troubleshooting (e.g. --extractor-args ...).

    Server-operator-only config (an env var, never client input), parsed once at startup
    with shlex so a malformed value fails fast with a clear ConfigurationError instead of
    surfacing as a confusing subprocess error on the first real request.
    """
    raw = _get(env, name)
    if not raw:
        return ()
    try:
        return tuple(shlex.split(raw))
    except ValueError as exc:
        raise ConfigurationError(f"{name} is not valid shell-style arguments: {exc}") from None


@dataclass(frozen=True)
class Config:
    env: str
    secret_key: str
    download_dir: Path
    temp_dir: Path
    min_free_disk_bytes: int
    max_total_storage_bytes: int
    max_file_size_bytes: int
    max_duration_seconds: int
    max_height: int
    max_concurrent_jobs: int
    max_queue_size: int
    info_timeout: int
    download_timeout: int
    max_request_bytes: int
    file_ttl_seconds: int
    job_record_ttl_seconds: int
    cleanup_interval: int
    ffmpeg_path: str | None
    require_ffmpeg: bool
    extra_ytdlp_args: tuple[str, ...]
    check_ytdlp_updates: bool
    log_level: str
    log_json: bool
    trusted_proxies: int
    rate_limit_info: str
    rate_limit_download: str
    rate_limit_status: str

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Config":
        env = os.environ if env is None else env
        app_env = (_get(env, "FLASK_ENV", "production") or "production").lower()
        if app_env not in {"production", "development", "testing"}:
            raise ConfigurationError("FLASK_ENV must be production, development or testing")

        secret = _get(env, "SECRET_KEY")
        if not secret:
            if app_env == "production":
                raise ConfigurationError("SECRET_KEY must be set when FLASK_ENV=production")
            secret = secrets.token_hex(32)

        level = (_get(env, "LOG_LEVEL", "INFO") or "INFO").upper()
        if level not in {"DEBUG", "INFO", "WARNING", "ERROR"}:
            raise ConfigurationError("LOG_LEVEL must be DEBUG, INFO, WARNING or ERROR")

        return cls(
            env=app_env,
            secret_key=secret,
            download_dir=_path(env, "DOWNLOAD_DIR", "downloads"),
            temp_dir=_path(env, "TEMP_DIR", "temp"),
            min_free_disk_bytes=_int(env, "MIN_FREE_DISK_MB", 1024, 0) * _MB,
            max_total_storage_bytes=_int(env, "MAX_TOTAL_STORAGE_MB", 2048, 0) * _MB,
            max_file_size_bytes=_int(env, "MAX_FILE_SIZE_MB", 1024) * _MB,
            max_duration_seconds=_int(env, "MAX_DURATION_SECONDS", 3600),
            max_height=_int(env, "MAX_HEIGHT", 2160, 144),
            max_concurrent_jobs=_int(env, "MAX_CONCURRENT_JOBS", 2),
            max_queue_size=_int(env, "MAX_QUEUE_SIZE", 8, 0),
            info_timeout=_int(env, "INFO_TIMEOUT", 45),
            download_timeout=_int(env, "DOWNLOAD_TIMEOUT", 600),
            max_request_bytes=_int(env, "MAX_REQUEST_BYTES", 16384),
            file_ttl_seconds=_int(env, "FILE_TTL_SECONDS", 900),
            job_record_ttl_seconds=_int(env, "JOB_RECORD_TTL_SECONDS", 3600),
            cleanup_interval=_int(env, "CLEANUP_INTERVAL", 60),
            ffmpeg_path=_get(env, "FFMPEG_PATH"),
            require_ffmpeg=_bool(env, "REQUIRE_FFMPEG", True),
            extra_ytdlp_args=_ytdlp_args(env, "EXTRA_YTDLP_ARGS"),
            check_ytdlp_updates=_bool(env, "CHECK_YTDLP_UPDATES", True),
            log_level=level,
            log_json=_bool(env, "LOG_JSON", True),
            trusted_proxies=_int(env, "TRUSTED_PROXIES", 0, 0),
            rate_limit_info=_get(env, "RATE_LIMIT_INFO", "15 per minute") or "15 per minute",
            rate_limit_download=_get(env, "RATE_LIMIT_DOWNLOAD", "5 per minute") or "5 per minute",
            rate_limit_status=_get(env, "RATE_LIMIT_STATUS", "120 per minute") or "120 per minute",
        )

    @property
    def is_production(self) -> bool:
        return self.env == "production"
