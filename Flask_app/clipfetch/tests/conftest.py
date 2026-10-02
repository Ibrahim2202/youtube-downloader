import shutil
import tempfile
from pathlib import Path

import pytest

from app import create_app
from app.config import Config
from app.services.ffmpeg import FFmpegInfo


@pytest.fixture()
def tmp_dirs():
    root = Path(tempfile.mkdtemp(prefix="clipfetch-test-"))
    (root / "downloads").mkdir()
    (root / "temp").mkdir()
    yield root
    shutil.rmtree(root, ignore_errors=True)


@pytest.fixture()
def config(tmp_dirs):
    env = {
        "FLASK_ENV": "testing",
        "SECRET_KEY": "test-secret",
        "DOWNLOAD_DIR": str(tmp_dirs / "downloads"),
        "TEMP_DIR": str(tmp_dirs / "temp"),
        "MAX_CONCURRENT_JOBS": "2",
        "REQUIRE_FFMPEG": "false",
    }
    return Config.from_env(env)


@pytest.fixture()
def app(config, monkeypatch):
    # Testing config skips the real ffmpeg check via REQUIRE_FFMPEG=false, but we still
    # want downloader.ffmpeg_available to reflect a "yes" so format-building tests exercise
    # the merge path; individual tests override where they need the "no ffmpeg" behaviour.
    monkeypatch.setattr("app.services.ffmpeg.check_ffmpeg",
                        lambda *a, **k: FFmpegInfo(path="/usr/bin/ffmpeg", version="ffmpeg 6.0"))
    flask_app = create_app(config)
    flask_app.config.update(TESTING=True)
    yield flask_app
    flask_app.extensions["clipfetch"].jobs.shutdown()


@pytest.fixture()
def client(app):
    return app.test_client()
