import pytest

from app.errors import InvalidRequest, InvalidURL, UnsupportedPlatform
from app.services.validation import normalize_url, validate_preset, validate_url


def test_normalize_adds_scheme():
    url, host = normalize_url("youtube.com/watch?v=abc")
    assert url.startswith("https://")
    assert host == "youtube.com"


@pytest.mark.parametrize("raw", ["", "   ", 123, None, ["a"]])
def test_rejects_empty_or_non_string(raw):
    with pytest.raises(InvalidURL):
        normalize_url(raw)


@pytest.mark.parametrize("raw", [
    "ftp://youtube.com/video",
    "javascript:alert(1)",
    "http://user:pass@youtube.com/video",
    "http://youtube.com:8080/video",
    "http://" + "a" * 3000 + ".com",
    "http://youtube.com/\x00video",
])
def test_rejects_malformed_or_dangerous_urls(raw):
    with pytest.raises(InvalidURL):
        normalize_url(raw)


def test_rejects_non_public_hosts(monkeypatch):
    from app.utils import security
    with pytest.raises(InvalidURL):
        security.assert_public_host("127.0.0.1")
    with pytest.raises(InvalidURL):
        security.assert_public_host("localhost")
    with pytest.raises(InvalidURL):
        security.assert_public_host("169.254.169.254")  # cloud metadata endpoint


def test_ssrf_blocks_hostname_resolving_to_private_ip(monkeypatch):
    from app.utils import security
    monkeypatch.setattr(security, "resolve_host", lambda host, port=443: ["10.0.0.5"])
    with pytest.raises(InvalidURL):
        security.assert_public_host("evil.example.com")


def test_unsupported_platform_rejected(monkeypatch):
    from app.services import validation
    monkeypatch.setattr(validation, "detect_platform", lambda url: None)
    monkeypatch.setattr("app.utils.security.assert_public_host", lambda host: None)
    with pytest.raises(UnsupportedPlatform):
        validate_url("https://example.com/video")


def test_supported_platform_accepted(monkeypatch):
    from app.services import validation
    monkeypatch.setattr(validation, "detect_platform", lambda url: "youtube")
    monkeypatch.setattr("app.utils.security.assert_public_host", lambda host: None)
    target = validate_url("https://youtube.com/watch?v=abc")
    assert target.platform == "youtube"


@pytest.mark.parametrize("preset", ["v720", "audio", "v1080"])
def test_valid_presets_accepted(preset):
    assert validate_preset(preset, max_height=1080) == preset


@pytest.mark.parametrize("preset", ["v99999", "../etc", "", None, 5, "v-720", "v720; rm -rf"])
def test_invalid_presets_rejected(preset):
    with pytest.raises(InvalidRequest):
        validate_preset(preset, max_height=1080)


def test_preset_above_max_height_rejected():
    with pytest.raises(InvalidRequest):
        validate_preset("v2160", max_height=1080)
