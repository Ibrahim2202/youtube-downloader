"""Resolves a small, explicit whitelist of first-party shortlink shapes (Facebook's
'/share/...' and 'fb.watch' links) to their real destination, so the security-motivated
exclusion of yt-dlp's generic extractor doesn't also break these very common share links.

This is NOT a general-purpose redirect follower: only the whitelisted hosts/paths below are
ever resolved, and every hop's host is re-checked against the SSRF guard before being
followed, so this can't be used to make the server fetch an arbitrary internal URL.
"""
from __future__ import annotations

import http.client
import socket
from urllib.parse import urljoin, urlsplit

from ..errors import NetworkError
from . import security

MAX_HOPS = 5
TIMEOUT_SECONDS = 8
_USER_AGENT = "Mozilla/5.0 (compatible; ClipFetchBot/1.0)"


def is_shortlink(host: str, path: str) -> bool:
    host = host.lower()
    if host in ("fb.watch",):
        return True
    if host in ("facebook.com", "www.facebook.com", "m.facebook.com", "web.facebook.com"):
        return path.startswith("/share/")
    return False


def fetch_redirect_location(url: str, timeout: float = TIMEOUT_SECONDS) -> tuple[int, str | None]:
    """Issue one GET (without reading the body) and return (status, Location header).

    A thin, mockable seam so tests can exercise the resolution loop without real sockets.
    """
    parts = urlsplit(url)
    conn_cls = http.client.HTTPSConnection if parts.scheme == "https" else http.client.HTTPConnection
    conn = conn_cls(parts.hostname, parts.port, timeout=timeout)
    try:
        path = (parts.path or "/") + (f"?{parts.query}" if parts.query else "")
        conn.request("GET", path, headers={"User-Agent": _USER_AGENT, "Accept": "*/*",
                                           "Connection": "close"})
        resp = conn.getresponse()
        resp.read(0)  # don't buffer the body; we only need headers
        return resp.status, resp.getheader("Location")
    finally:
        conn.close()


def resolve_shortlink(url: str) -> str:
    """Follow redirects from a whitelisted shortlink to its real destination.

    Every intermediate host is validated as public before being followed. Raises
    NetworkError on connection failure so the caller reports an honest, retryable error
    instead of a confusing "unsupported platform".
    """
    current = url
    for _ in range(MAX_HOPS):
        try:
            status, location = fetch_redirect_location(current)
        except (OSError, socket.timeout, http.client.HTTPException) as exc:
            raise NetworkError(f"could not resolve shortlink {current}: {exc}") from exc
        if status not in (301, 302, 303, 307, 308) or not location:
            return current
        next_url = urljoin(current, location)
        next_host = urlsplit(next_url).hostname
        if not next_host:
            return current
        security.assert_public_host(next_host)  # re-guard every hop, not just the first
        current = next_url
    return current
