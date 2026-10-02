import pytest

from app.errors import (ExtractionError, FFmpegError, MediaUnavailable, PlatformAccessDenied,
                        RateLimitError)
from app.errors import classify_ytdlp_failure
from app.services.downloader import build_format_args
from app.services.ffmpeg import check_ffmpeg, locate_ffmpeg


@pytest.mark.parametrize("message,expected", [
    ("ERROR: [youtube] abc: Sign in to confirm you're not a bot", PlatformAccessDenied),
    ("ERROR: Private video. Sign in if you've been granted access", MediaUnavailable),
    ("ERROR: Video unavailable. This video has been removed", MediaUnavailable),
    ("ERROR: HTTP Error 429: Too Many Requests", RateLimitError),
    ("ERROR: unable to download video data: HTTP Error 403: Forbidden", PlatformAccessDenied),
    ("Something totally unrecognized happened", ExtractionError),
])
def test_classify_ytdlp_failure(message, expected):
    assert isinstance(classify_ytdlp_failure(message), expected)


def test_classify_unmatched_tiktok_failure_gets_specific_hint():
    err = classify_ytdlp_failure("Something totally unrecognized happened", platform="tiktok")
    assert isinstance(err, ExtractionError)
    assert "tiktok" in err.user_message.lower()


def test_classify_unmatched_failure_without_platform_gets_generic_message():
    err = classify_ytdlp_failure("Something totally unrecognized happened")
    assert "try again later" in err.user_message.lower()


def test_classify_matched_failure_ignores_platform_hint():
    # A recognized pattern should win regardless of platform -- the hint is fallback-only.
    err = classify_ytdlp_failure("ERROR: HTTP Error 429: Too Many Requests", platform="tiktok")
    assert isinstance(err, RateLimitError)


def test_classify_never_leaks_full_output_beyond_tail():
    huge = "x" * 5000 + "HTTP Error 429: Too Many Requests"
    err = classify_ytdlp_failure(huge)
    assert len(err.detail) <= 801


def test_build_format_args_audio_with_ffmpeg():
    args = build_format_args("audio", ffmpeg_available=True)
    assert "-x" in args and "mp3" in args


def test_build_format_args_audio_without_ffmpeg():
    args = build_format_args("audio", ffmpeg_available=False)
    assert "-x" not in args


def test_build_format_args_video_height_bound():
    args = build_format_args("v720", ffmpeg_available=True)
    joined = " ".join(args)
    assert "height<=?720" in joined


def test_locate_ffmpeg_missing_binary_returns_none():
    assert locate_ffmpeg("/definitely/not/a/real/ffmpeg/binary") is None


def test_check_ffmpeg_raises_clear_error_when_missing():
    with pytest.raises(FFmpegError):
        check_ffmpeg("/definitely/not/a/real/ffmpeg/binary")
