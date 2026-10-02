"""Structured application errors and yt-dlp failure classification.

Every error carries a stable machine code, an HTTP status, and a safe
user-facing message. `detail` holds diagnostics for server logs only.
"""
from __future__ import annotations

import re


class AppError(Exception):
    code = "internal_error"
    http_status = 500
    retryable = False
    user_message = "Something went wrong on our side. Please try again in a moment."

    def __init__(self, detail: str | None = None, *, user_message: str | None = None):
        super().__init__(detail or self.user_message)
        self.detail = detail
        if user_message:
            self.user_message = user_message

    def to_dict(self) -> dict:
        return {"code": self.code, "message": self.user_message, "retryable": self.retryable}


class ConfigurationError(AppError):
    code = "configuration_error"
    user_message = "The server is misconfigured."


class InvalidRequest(AppError):
    code, http_status = "invalid_request", 400
    user_message = "The request was malformed."


class InvalidURL(AppError):
    code, http_status = "invalid_url", 400
    user_message = "That doesn't look like a valid public video link. Check the URL and try again."


class UnsupportedPlatform(AppError):
    code, http_status = "unsupported_platform", 422
    user_message = "This website isn't supported."


class MediaUnavailable(AppError):
    code, http_status = "media_unavailable", 422
    user_message = ("This video is private, removed, age-restricted, live, or not available "
                    "from this server's region.")


class MediaTooLong(AppError):
    code, http_status = "media_too_long", 422
    user_message = "This video is longer than the maximum duration this service allows."


class FileTooLarge(AppError):
    code, http_status = "file_too_large", 413
    user_message = "The file would exceed this service's size limit. Try a lower quality."


class ExtractionError(AppError):
    code, http_status, retryable = "extraction_error", 502, True
    user_message = ("Couldn't read this video from the platform. The site may have changed; "
                    "please try again later.")


class PlatformAccessDenied(AppError):
    code, http_status = "platform_access_denied", 502
    user_message = ("Your request was rejected by the video platform from this server. "
                    "Please try again later or use a source that permits this type of access.")


class RateLimitError(AppError):
    code, http_status, retryable = "platform_rate_limited", 429, True
    user_message = "The video platform is limiting requests from this server. Wait a while and try again."


class NetworkError(AppError):
    code, http_status, retryable = "network_error", 504, True
    user_message = "The server couldn't reach the video platform. Please try again."


class DownloadTimeout(AppError):
    code, http_status, retryable = "timeout", 504, True
    user_message = "The operation took too long and was cancelled. Try again or pick a lower quality."


class FFmpegError(AppError):
    code, http_status = "ffmpeg_error", 500
    user_message = "Processing the media failed on the server."


class StorageError(AppError):
    code, http_status, retryable = "storage_error", 507, True
    user_message = "The server is low on storage right now. Please try again later."


class ServerBusy(AppError):
    code, http_status, retryable = "server_busy", 503, True
    user_message = "The server is busy with other downloads. Please try again in a minute."


class JobNotFound(AppError):
    code, http_status = "job_not_found", 404
    user_message = "That download doesn't exist or has expired."


class JobNotReady(AppError):
    code, http_status, retryable = "job_not_ready", 409, True
    user_message = "That file isn't ready yet."


class FileExpired(AppError):
    code, http_status = "file_expired", 410
    user_message = "This file has expired and was deleted. Start the download again."


# Order matters: first match wins. Patterns are matched against yt-dlp output (case-insensitive).
_RULES: list[tuple[str, type[AppError]]] = [
    (r"no space left|errno 28|disk quota", StorageError),
    (r"larger than max-filesize", FileTooLarge),
    (r"does not pass filter", MediaTooLong),
    # Bot checks / IP rejection must precede the generic "unavailable" and "sign in" rules.
    (r"not a bot|captcha|verify you are human|rate-limit reached or login required|"
     r"content isn.t available, try again later", PlatformAccessDenied),
    (r"private video|video unavailable|has been removed|no longer available|been deleted|"
     r"not available in your country|blocked it|members.only|age-restricted|confirm your age|"
     r"this video is not available|removed by the uploader|account .* terminated|"
     r"is not available|live event will begin|is live", MediaUnavailable),
    (r"http error 429|too many requests|rate.?limit", RateLimitError),
    (r"http error 40[13]|forbidden|login required|log in|sign in|cookies|authentication",
     PlatformAccessDenied),
    (r"unsupported url", UnsupportedPlatform),
    (r"ffmpeg|ffprobe|postprocessing|merger", FFmpegError),
    (r"timed out|timeout", DownloadTimeout),
    (r"name resolution|connection (refused|reset|aborted)|network is unreachable|"
     r"unable to download (webpage|json)|remote end closed|ssl", NetworkError),
]

# When nothing above matches, the fallback message can still be more useful than a flat
# "couldn't read this video" if we know which platform's extractor failed -- some platforms
# (TikTok especially) change their anti-automation measures often enough that an unmatched
# failure is more likely to be "the extractor needs an update" than a one-off fluke.
_PLATFORM_FALLBACK_HINTS: dict[str, str] = {
    "tiktok": ("TikTok rejected or changed how this video is served. This usually means "
              "TikTok's anti-bot measures changed faster than the downloader's TikTok "
              "support -- updating yt-dlp (`pip install -U yt-dlp`) fixes this more often "
              "than any other single step. If it's already up to date, this is most likely "
              "a temporary gap on TikTok's side rather than a bug in this server."),
    "instagram": ("Instagram rejected or changed how this post is served. Instagram is "
                 "particularly aggressive about automated access; try again later, or "
                 "update yt-dlp if this persists."),
}


def classify_ytdlp_failure(output: str, platform: str | None = None) -> AppError:
    """Map raw yt-dlp output to a typed error. The raw text is kept as `detail` (logs only).

    `platform` (a yt-dlp extractor name, e.g. "tiktok") only affects the *fallback* message
    used when no specific pattern above matches -- it never changes the error's HTTP status
    or code, only makes the generic case more actionable for platforms known to break often.
    """
    text = (output or "").strip()
    tail = text[-800:]
    for pattern, error_cls in _RULES:
        if re.search(pattern, text, re.IGNORECASE):
            return error_cls(tail)
    hint = _PLATFORM_FALLBACK_HINTS.get((platform or "").lower())
    return ExtractionError(tail, user_message=hint) if hint else ExtractionError(tail)
