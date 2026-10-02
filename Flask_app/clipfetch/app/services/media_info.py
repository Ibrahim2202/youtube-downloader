"""Turn raw yt-dlp metadata into a safe, minimal description plus server-defined quality presets."""
from __future__ import annotations

from dataclasses import dataclass, field

from ..config import Config
from ..errors import FileTooLarge, InvalidURL, MediaTooLong, MediaUnavailable

_DISPLAY_NAMES = {"youtube": "YouTube", "tiktok": "TikTok", "instagram": "Instagram",
                  "facebook": "Facebook", "twitter": "X / Twitter", "reddit": "Reddit",
                  "vimeo": "Vimeo", "twitch:clips": "Twitch"}


@dataclass
class FormatOption:
    id: str
    label: str
    kind: str  # "video" | "audio"
    filesize: int | None = None

    def to_dict(self) -> dict:
        return {"id": self.id, "label": self.label, "kind": self.kind, "filesize": self.filesize}


@dataclass
class MediaInfo:
    title: str
    platform: str
    thumbnail: str | None
    duration: int | None
    uploader: str | None
    formats: list[FormatOption] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {"title": self.title, "platform": self.platform, "thumbnail": self.thumbnail,
                "duration": self.duration, "uploader": self.uploader,
                "formats": [f.to_dict() for f in self.formats]}


def display_platform(name: str) -> str:
    return _DISPLAY_NAMES.get(name.lower(), name.replace(":", " ").title())


def _size(fmt: dict) -> int | None:
    value = fmt.get("filesize") or fmt.get("filesize_approx")
    return int(value) if isinstance(value, (int, float)) and value > 0 else None


def _has(fmt: dict, key: str) -> bool:
    return fmt.get(key) not in (None, "none")


def parse_media_info(raw: dict, *, platform: str, config: Config, ffmpeg_available: bool) -> MediaInfo:
    if raw.get("_type") in ("playlist", "multi_video"):
        raise InvalidURL("playlist url", user_message="Playlists and channels aren't supported. "
                                                      "Paste a link to a single video.")
    if raw.get("is_live") or raw.get("live_status") in ("is_live", "is_upcoming"):
        raise MediaUnavailable("live stream")
    duration = raw.get("duration")
    duration = int(duration) if isinstance(duration, (int, float)) else None
    if duration and duration > config.max_duration_seconds:
        raise MediaTooLong(f"duration {duration}s")

    formats = [f for f in (raw.get("formats") or []) if isinstance(f, dict)]
    audio_only = [f for f in formats if _has(f, "acodec") and not _has(f, "vcodec")]
    video = [f for f in formats if _has(f, "vcodec") and isinstance(f.get("height"), int)]
    if not ffmpeg_available:  # can only serve single-file (progressive) formats
        video = [f for f in video if _has(f, "acodec")]
    best_audio = max((s for s in map(_size, audio_only) if s), default=None)

    options: list[FormatOption] = []
    for height in sorted({f["height"] for f in video}, reverse=True):
        if height > config.max_height:
            continue
        sizes = [s for s in (_size(f) for f in video if f["height"] == height) if s]
        total = (max(sizes) + (best_audio or 0)) if sizes else None
        if total and total > config.max_file_size_bytes:
            continue
        options.append(FormatOption(f"v{height}", f"{height}p MP4", "video", total))
    if not options and not audio_only and not video and not formats:
        options.append(FormatOption(f"v{config.max_height}", "Best available", "video", None))

    if audio_only or video or not formats:
        options.append(FormatOption("audio", "Audio only (MP3)" if ffmpeg_available
                                    else "Audio only (original)", "audio", best_audio))
    if not options:
        raise FileTooLarge("every format exceeds the size limit")

    thumb = raw.get("thumbnail")
    return MediaInfo(
        title=str(raw.get("title") or "Untitled video")[:300],
        platform=display_platform(platform),
        thumbnail=thumb if isinstance(thumb, str) and thumb.startswith("https://") else None,
        duration=duration,
        uploader=(str(raw["uploader"])[:120] if raw.get("uploader") else None),
        formats=options,
    )
