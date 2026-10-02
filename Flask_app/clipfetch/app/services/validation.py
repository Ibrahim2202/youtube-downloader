"""URL and request-parameter validation. All user input is treated as hostile."""
from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from urllib.parse import urlsplit, urlunsplit

from ..errors import InvalidRequest, InvalidURL, UnsupportedPlatform
from ..utils import security
from ..utils.redirect import is_shortlink, resolve_shortlink

MAX_URL_LENGTH = 2048
ALLOWED_SCHEMES = {"http", "https"}
ALLOWED_PORTS = {None, 80, 443}
_PRESET_RE = re.compile(r"^(audio|v([1-9]\d{2,3}))$")


@dataclass(frozen=True)
class ValidatedURL:
    url: str
    host: str
    platform: str  # yt-dlp extractor name, e.g. "youtube"


def normalize_url(raw: object) -> tuple[str, str]:
    """Return (normalized_url, ascii_host) or raise InvalidURL."""
    if not isinstance(raw, str):
        raise InvalidURL("url is not a string")
    text = raw.strip()
    if not text:
        raise InvalidURL("empty url", user_message="Paste a video link first.")
    if len(text) > MAX_URL_LENGTH:
        raise InvalidURL("url too long")
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in text):
        raise InvalidURL("whitespace/control characters in url")
    if "://" not in text:
        text = "https://" + text

    try:
        parts = urlsplit(text)
        port = parts.port
        host = parts.hostname
    except ValueError:
        raise InvalidURL("unparseable url") from None
    if parts.scheme.lower() not in ALLOWED_SCHEMES:
        raise InvalidURL(f"scheme not allowed: {parts.scheme}")
    if not host:
        raise InvalidURL("missing host")
    if parts.username is not None or parts.password is not None:
        raise InvalidURL("credentials in url")
    if port not in ALLOWED_PORTS:
        raise InvalidURL(f"port not allowed: {port}")
    try:
        host = host.rstrip(".").lower().encode("idna").decode("ascii")
    except UnicodeError:
        raise InvalidURL("invalid hostname") from None

    netloc = f"[{host}]" if ":" in host else host
    if port:
        netloc += f":{port}"
    url = urlunsplit((parts.scheme.lower(), netloc, parts.path or "/", parts.query, ""))
    return url, host


@lru_cache(maxsize=1)
def _extractor_classes() -> tuple:
    from yt_dlp.extractor import gen_extractor_classes
    return tuple(ie for ie in gen_extractor_classes() if ie.IE_NAME != "generic" and ie.working())


def detect_platform(url: str) -> str | None:
    """Name of the dedicated yt-dlp extractor for this URL, or None.

    The generic extractor is deliberately excluded: it fetches arbitrary pages and would
    turn the server into a general-purpose fetcher (SSRF surface).
    """
    for ie in _extractor_classes():
        if ie.suitable(url):
            return ie.IE_NAME
    return None


def validate_url(raw: object) -> ValidatedURL:
    url, host = normalize_url(raw)
    security.assert_public_host(host)
    path = urlsplit(url).path
    if is_shortlink(host, path):
        resolved = resolve_shortlink(url)
        if resolved != url:
            url, host = normalize_url(resolved)
            security.assert_public_host(host)
    platform = detect_platform(url)
    if platform is None:
        raise UnsupportedPlatform(f"no dedicated extractor for host {host}")
    return ValidatedURL(url=url, host=host, platform=platform)


def validate_preset(value: object, max_height: int) -> str:
    """Accept only server-known preset IDs ('audio' or 'v<height>')."""
    if not isinstance(value, str) or not _PRESET_RE.match(value):
        raise InvalidRequest(f"bad format_id: {value!r}", user_message="Choose a valid quality option.")
    if value != "audio" and int(value[1:]) > max_height:
        raise InvalidRequest("format above max height", user_message="That quality isn't available.")
    return value
