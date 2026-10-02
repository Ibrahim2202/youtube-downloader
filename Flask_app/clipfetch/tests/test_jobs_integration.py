"""Exercises the real JobManager thread pool + file move + serving path.

The network call itself (yt-dlp -> platform) is stubbed, per the spec's own requirement
not to depend on live downloads in automated tests; everything else here is real.
"""
import time

import pytest

from app.errors import PlatformAccessDenied
from app.services.downloader import DownloadResult
from app.services.validation import ValidatedURL


def _target():
    return ValidatedURL(url="https://youtube.com/watch?v=abc", host="youtube.com", platform="youtube")


def _wait_for(jobs, job_id, terminal_statuses, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        job = jobs.get(job_id)
        if job.status.value in terminal_statuses:
            return job
        time.sleep(0.02)
    raise AssertionError("job did not reach a terminal state in time")


def test_full_job_lifecycle_success(app, client, monkeypatch, tmp_path):
    services = app.extensions["clipfetch"]
    fake_file = tmp_path / "media.mp4"
    fake_file.write_bytes(b"fake video bytes")

    def fake_download(target, preset, job_dir, on_progress):
        on_progress(50.0, "downloading")
        on_progress(None, "processing")
        return DownloadResult(path=fake_file, file_name="My Video.mp4", size=fake_file.stat().st_size,
                              title="My Video")

    monkeypatch.setattr(services.downloader, "validate_url", lambda raw: _target())
    monkeypatch.setattr(services.downloader, "download", fake_download)
    monkeypatch.setattr(services.downloader, "cleanup", lambda job_dir: None)

    res = client.post("/api/download", json={"url": "https://youtube.com/watch?v=abc", "format_id": "v720"})
    job_id = res.get_json()["job_id"]

    job = _wait_for(services.jobs, job_id, {"completed", "failed"})
    assert job.status.value == "completed"
    assert job.file_path.is_file()
    assert job.file_path.read_bytes() == b"fake video bytes"

    status = client.get(f"/api/download/{job_id}").get_json()
    assert status["status"] == "completed"
    assert status["file_name"] == "My Video.mp4"
    assert status["expires_in"] > 0

    file_res = client.get(f"/api/download/{job_id}/file")
    assert file_res.status_code == 200
    assert file_res.data == b"fake video bytes"


def test_full_job_lifecycle_failure_is_classified(app, client, monkeypatch):
    services = app.extensions["clipfetch"]

    def fake_download(target, preset, job_dir, on_progress):
        raise PlatformAccessDenied("simulated bot check")

    monkeypatch.setattr(services.downloader, "validate_url", lambda raw: _target())
    monkeypatch.setattr(services.downloader, "download", fake_download)
    monkeypatch.setattr(services.downloader, "cleanup", lambda job_dir: None)

    res = client.post("/api/download", json={"url": "https://youtube.com/watch?v=abc", "format_id": "v720"})
    job_id = res.get_json()["job_id"]

    job = _wait_for(services.jobs, job_id, {"completed", "failed"})
    assert job.status.value == "failed"
    assert job.error["code"] == "platform_access_denied"

    status = client.get(f"/api/download/{job_id}").get_json()
    assert status["status"] == "failed"
    assert status["error"]["code"] == "platform_access_denied"

    file_res = client.get(f"/api/download/{job_id}/file")
    assert file_res.status_code == 404


def test_server_busy_when_queue_full(app, client, monkeypatch):
    services = app.extensions["clipfetch"]
    # The route itself is rate-limited separately from the job queue; lift that limit so
    # this test isolates JobManager's own "server busy" behaviour.
    services.config.__dict__ if False else None
    monkeypatch.setattr("app.routes.api.limiter.enabled", False)
    monkeypatch.setattr(services.downloader, "validate_url", lambda raw: _target())

    gate = __import__("threading").Event()

    def blocking_download(*a, **k):
        gate.wait(5)
        raise PlatformAccessDenied("x")

    monkeypatch.setattr(services.downloader, "download", blocking_download)
    monkeypatch.setattr(services.downloader, "cleanup", lambda job_dir: None)

    total_slots = services.config.max_concurrent_jobs + services.config.max_queue_size
    codes = []
    try:
        for _ in range(total_slots + 2):
            res = client.post("/api/download", json={"url": "https://youtube.com/watch?v=abc", "format_id": "v720"})
            codes.append(res.status_code)
    finally:
        gate.set()
    assert 503 in codes
