#!/usr/bin/env python3
"""Diagnose why a URL fails, using the exact same yt-dlp invocation the app uses.

Usage:
    python scripts/diagnose.py "https://www.tiktok.com/@user/video/123..."

Prints the platform detected, the full yt-dlp command run, and yt-dlp's raw verbose
output. Paste that output back when reporting an extraction problem -- it's the fastest
way to get an exact, non-guessed fix instead of a generic "try updating yt-dlp".
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(override=False)

from app.config import Config  # noqa: E402
from app.services.validation import validate_url  # noqa: E402


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <url>", file=sys.stderr)
        return 2
    url = sys.argv[1]

    try:
        config = Config.from_env()
    except Exception as exc:  # noqa: BLE001
        print(f"Could not load configuration (check .env): {exc}", file=sys.stderr)
        return 2

    try:
        target = validate_url(url)
    except Exception as exc:  # noqa: BLE001
        print(f"This app would reject that URL before even calling yt-dlp: {exc}")
        return 1
    print(f"Detected platform: {target.platform}")
    print(f"Normalized URL:    {target.url}\n")

    cmd = [sys.executable, "-m", "yt_dlp", "--ignore-config", "--no-playlist", "-v",
           "--dump-single-json", "--skip-download"]
    if config.extra_ytdlp_args:
        cmd += list(config.extra_ytdlp_args)
    cmd += ["--", target.url]
    print("Running:", " ".join(cmd), "\n" + "-" * 60)

    result = subprocess.run(cmd, timeout=90)
    print("-" * 60)
    print(f"\nExit code: {result.returncode}")
    print("Copy everything above (especially any line starting with ERROR:) and share it "
          "for an exact diagnosis.")
    return result.returncode


if __name__ == "__main__":
    raise SystemExit(main())
