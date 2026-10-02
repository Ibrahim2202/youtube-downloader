"""One-shot startup check: is the pinned yt-dlp current? Never blocks or fails startup --
this is advisory logging only, since a deployment with restricted outbound networking
(see README) may not be able to reach PyPI at all, and that's not a reason to refuse to boot.
"""
from __future__ import annotations

import json
import logging
import urllib.request
from importlib.metadata import PackageNotFoundError, version

logger = logging.getLogger("clipfetch.startup")
_PYPI_URL = "https://pypi.org/pypi/yt-dlp/json"
_TIMEOUT = 3.0


def check_ytdlp_current() -> None:
    try:
        installed = version("yt-dlp")
    except PackageNotFoundError:
        return
    try:
        with urllib.request.urlopen(_PYPI_URL, timeout=_TIMEOUT) as resp:
            latest = json.loads(resp.read())["info"]["version"]
    except Exception as exc:  # noqa: BLE001 - advisory only, any failure here is non-fatal
        logger.debug("yt-dlp update check skipped (%s)", exc)
        return
    if installed != latest:
        logger.warning(
            "yt-dlp %s is installed but %s is available on PyPI. Platform extractors "
            "(TikTok and Instagram especially) break often enough that this is the single "
            "most common fix for extraction failures -- run: pip install -U yt-dlp==%s "
            "and update the pin in requirements.txt.", installed, latest, latest)
    else:
        logger.info("yt-dlp %s is up to date.", installed)


def check_impersonation_available() -> None:
    """Warn if yt-dlp has no browser-impersonation backend (curl_cffi).

    TikTok's extractor requests impersonation automatically; without a backend installed,
    every TikTok request goes out with a plain urllib fingerprint that TikTok's bot
    detection is far more likely to flag. This has no fix action beyond "install
    curl_cffi", which is already pinned in requirements.txt -- this check exists purely to
    catch the case where it failed to install (e.g. missing build tools on an unusual host).
    """
    try:
        import curl_cffi  # noqa: F401
        logger.info("browser-impersonation backend available (curl_cffi).")
    except ImportError:
        logger.warning(
            "curl_cffi is not installed/importable. yt-dlp will fall back to a plain HTTP "
            "fingerprint for sites that request browser impersonation (TikTok in "
            "particular), which is significantly more likely to be blocked. Run: "
            "pip install curl_cffi (already pinned in requirements.txt -- check for an "
            "install error, it sometimes needs build tools on unusual platforms).")
