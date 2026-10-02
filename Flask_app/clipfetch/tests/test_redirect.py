import pytest

from app.errors import InvalidURL, NetworkError
from app.utils import redirect, security
from app.utils.redirect import is_shortlink, resolve_shortlink


@pytest.mark.parametrize("host,path,expected", [
    ("fb.watch", "/abc123/", True),
    ("facebook.com", "/share/r/abc123/", True),
    ("www.facebook.com", "/share/v/abc123/", True),
    ("facebook.com", "/watch/?v=123", False),
    ("youtube.com", "/share/x", False),
    ("evil.com", "/share/", False),
])
def test_is_shortlink(host, path, expected):
    assert is_shortlink(host, path) is expected


def test_resolve_shortlink_follows_single_redirect(monkeypatch):
    calls = []

    def fake_fetch(url, timeout=8):
        calls.append(url)
        if url == "https://fb.watch/abc/":
            return 302, "https://www.facebook.com/reel/998877/"
        return 200, None

    monkeypatch.setattr(redirect, "fetch_redirect_location", fake_fetch)
    monkeypatch.setattr(security, "assert_public_host", lambda host: None)
    result = resolve_shortlink("https://fb.watch/abc/")
    assert result == "https://www.facebook.com/reel/998877/"
    assert calls == ["https://fb.watch/abc/", "https://www.facebook.com/reel/998877/"]


def test_resolve_shortlink_stops_at_max_hops(monkeypatch):
    def fake_fetch(url, timeout=8):
        n = int(url.rsplit("/", 1)[-1])
        return 302, f"https://fb.watch/{n + 1}"

    monkeypatch.setattr(redirect, "fetch_redirect_location", fake_fetch)
    monkeypatch.setattr(security, "assert_public_host", lambda host: None)
    result = resolve_shortlink("https://fb.watch/0")
    assert result == f"https://fb.watch/{redirect.MAX_HOPS}"


def test_resolve_shortlink_rejects_redirect_to_private_host(monkeypatch):
    def fake_fetch(url, timeout=8):
        return 302, "http://169.254.169.254/latest/meta-data/"

    monkeypatch.setattr(redirect, "fetch_redirect_location", fake_fetch)
    with pytest.raises(InvalidURL):
        resolve_shortlink("https://fb.watch/abc/")


def test_resolve_shortlink_wraps_connection_errors(monkeypatch):
    def fake_fetch(url, timeout=8):
        raise OSError("connection refused")

    monkeypatch.setattr(redirect, "fetch_redirect_location", fake_fetch)
    with pytest.raises(NetworkError):
        resolve_shortlink("https://fb.watch/abc/")


def test_non_redirect_response_returns_original_url(monkeypatch):
    monkeypatch.setattr(redirect, "fetch_redirect_location", lambda url, timeout=8: (200, None))
    assert resolve_shortlink("https://fb.watch/abc/") == "https://fb.watch/abc/"


def test_validate_url_resolves_facebook_share_link(monkeypatch):
    from app.services import validation

    monkeypatch.setattr(security, "assert_public_host", lambda host: None)
    monkeypatch.setattr(validation, "resolve_shortlink",
                        lambda url: "https://www.facebook.com/reel/998877/")
    monkeypatch.setattr(validation, "detect_platform", lambda url: "facebook" if "reel" in url else None)

    target = validation.validate_url("https://www.facebook.com/share/r/abc123/")
    assert target.platform == "facebook"
    assert target.url == "https://www.facebook.com/reel/998877/"
