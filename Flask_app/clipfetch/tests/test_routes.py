import io
import json
from unittest.mock import MagicMock

import pytest

from app.errors import MediaUnavailable, PlatformAccessDenied, UnsupportedPlatform
from app.services.media_info import FormatOption, MediaInfo
from app.services.validation import ValidatedURL


def _target():
    return ValidatedURL(url="https://youtube.com/watch?v=abc", host="youtube.com", platform="youtube")


def test_index_page_renders(client):
    res = client.get("/")
    assert res.status_code == 200
    assert b"ClipFetch" in res.data


def test_health_endpoint(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.get_json()["success"] is True


def test_info_rejects_missing_body(client):
    res = client.post("/api/info")
    assert res.status_code == 400
    assert res.get_json()["error"]["code"] == "invalid_request"


def test_info_rejects_invalid_url(client):
    res = client.post("/api/info", json={"url": "not a url"})
    assert res.status_code == 400
    assert res.get_json()["success"] is False


def test_info_returns_media_on_success(app, client, monkeypatch):
    services = app.extensions["clipfetch"]
    media = MediaInfo(title="Test video", platform="YouTube", thumbnail=None, duration=42,
                      uploader="Someone", formats=[FormatOption("v720", "720p MP4", "video", 1000)])
    monkeypatch.setattr(services.downloader, "validate_url", lambda raw: _target())
    monkeypatch.setattr(services.downloader, "extract_info", lambda target: media)
    res = client.post("/api/info", json={"url": "https://youtube.com/watch?v=abc"})
    body = res.get_json()
    assert res.status_code == 200
    assert body["title"] == "Test video"
    assert body["formats"][0]["id"] == "v720"


def test_info_maps_platform_access_denied_to_502(app, client, monkeypatch):
    services = app.extensions["clipfetch"]
    monkeypatch.setattr(services.downloader, "validate_url", lambda raw: _target())

    def boom(target):
        raise PlatformAccessDenied("blocked")
    monkeypatch.setattr(services.downloader, "extract_info", boom)
    res = client.post("/api/info", json={"url": "https://youtube.com/watch?v=abc"})
    assert res.status_code == 502
    assert res.get_json()["error"]["code"] == "platform_access_denied"


def test_info_maps_media_unavailable_to_422(app, client, monkeypatch):
    services = app.extensions["clipfetch"]
    monkeypatch.setattr(services.downloader, "validate_url", lambda raw: _target())

    def boom(target):
        raise MediaUnavailable("private")
    monkeypatch.setattr(services.downloader, "extract_info", boom)
    res = client.post("/api/info", json={"url": "https://youtube.com/watch?v=abc"})
    assert res.status_code == 422


def test_download_rejects_bad_format_id(app, client, monkeypatch):
    services = app.extensions["clipfetch"]
    monkeypatch.setattr(services.downloader, "validate_url", lambda raw: _target())
    res = client.post("/api/download", json={"url": "https://youtube.com/watch?v=abc",
                                             "format_id": "../../etc/passwd"})
    assert res.status_code == 400


def test_download_queues_job(app, client, monkeypatch):
    services = app.extensions["clipfetch"]
    monkeypatch.setattr(services.downloader, "validate_url", lambda raw: _target())
    monkeypatch.setattr(services.jobs, "_run", lambda job_id: None)  # never actually run
    res = client.post("/api/download", json={"url": "https://youtube.com/watch?v=abc",
                                             "format_id": "v720"})
    assert res.status_code == 202
    body = res.get_json()
    assert body["success"] is True
    assert len(body["job_id"]) == 32


def test_job_status_unknown_job_404s(client):
    res = client.get("/api/download/" + "a" * 32)
    assert res.status_code == 404


def test_job_status_invalid_id_shape_404s(client):
    res = client.get("/api/download/not-a-real-id")
    assert res.status_code == 404


def test_job_file_not_ready_yet(app, client, monkeypatch):
    services = app.extensions["clipfetch"]
    monkeypatch.setattr(services.downloader, "validate_url", lambda raw: _target())
    monkeypatch.setattr(services.jobs, "_run", lambda job_id: None)
    res = client.post("/api/download", json={"url": "https://youtube.com/watch?v=abc",
                                             "format_id": "v720"})
    job_id = res.get_json()["job_id"]
    res = client.get(f"/api/download/{job_id}/file")
    assert res.status_code == 409


def test_oversized_body_rejected(client):
    huge_url = "https://youtube.com/watch?v=" + "a" * 20000
    res = client.post("/api/info", json={"url": huge_url})
    assert res.status_code in (400, 413)
