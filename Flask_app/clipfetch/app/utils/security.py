"""SSRF protection: only URLs whose host resolves exclusively to public IPs are accepted."""
from __future__ import annotations

import ipaddress
import socket

from ..errors import InvalidURL

_BLOCKED_SUFFIXES = (".localhost", ".local", ".internal", ".localdomain", ".lan", ".home.arpa")


def resolve_host(host: str, port: int = 443) -> list[str]:
    """Resolve a hostname to its IP addresses (separate function so tests can patch it)."""
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (socket.gaierror, UnicodeError):
        return []
    return sorted({info[4][0] for info in infos})


def is_public_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def assert_public_host(host: str) -> None:
    """Raise InvalidURL unless `host` is (or resolves only to) public addresses."""
    if host == "localhost" or host.endswith(_BLOCKED_SUFFIXES):
        raise InvalidURL(f"blocked local hostname: {host}")
    try:
        addresses = [ipaddress.ip_address(host)]
    except ValueError:
        addresses = []
        for raw in resolve_host(host):
            try:
                addresses.append(ipaddress.ip_address(raw.split("%")[0]))
            except ValueError:
                continue
    if not addresses:
        raise InvalidURL(f"host does not resolve: {host}",
                         user_message="That website's address couldn't be found. Check the URL.")
    if not all(is_public_ip(ip) for ip in addresses):
        raise InvalidURL(f"host resolves to non-public address: {host}")
