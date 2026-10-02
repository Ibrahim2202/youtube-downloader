import pytest

from app.errors import StorageError
from app.services.validation import ValidatedURL


def _target():
    return ValidatedURL(url="https://youtube.com/watch?v=abc", host="youtube.com", platform="youtube")


def test_submit_rejects_when_total_storage_cap_would_be_exceeded(app, client, monkeypatch):
    services = app.extensions["clipfetch"]
    monkeypatch.setattr(services.downloader, "validate_url", lambda raw: _target())
    monkeypatch.setattr(services.jobs, "_run", lambda job_id: None)

    # Pretend downloads/+temp/ are already nearly at the configured cap.
    almost_full = services.config.max_total_storage_bytes - 100
    monkeypatch.setattr("app.services.jobs.directory_size", lambda path: almost_full // 2)

    res = client.post("/api/download", json={"url": "https://youtube.com/watch?v=abc", "format_id": "v720"})
    assert res.status_code == 507
    assert res.get_json()["error"]["code"] == "storage_error"


def test_submit_allows_when_well_under_cap(app, client, monkeypatch):
    services = app.extensions["clipfetch"]
    monkeypatch.setattr(services.downloader, "validate_url", lambda raw: _target())
    monkeypatch.setattr(services.jobs, "_run", lambda job_id: None)
    monkeypatch.setattr("app.services.jobs.directory_size", lambda path: 0)

    res = client.post("/api/download", json={"url": "https://youtube.com/watch?v=abc", "format_id": "v720"})
    assert res.status_code == 202


def test_directory_size_sums_files_recursively(tmp_path):
    from app.utils.helpers import directory_size

    (tmp_path / "a").mkdir()
    (tmp_path / "a" / "f1.bin").write_bytes(b"x" * 100)
    (tmp_path / "b.bin").write_bytes(b"y" * 50)
    assert directory_size(tmp_path) == 150


def test_directory_size_missing_dir_returns_zero(tmp_path):
    from app.utils.helpers import directory_size
    assert directory_size(tmp_path / "does-not-exist") == 0
