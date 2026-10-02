import pytest

from app.config import Config
from app.errors import ConfigurationError


def _env(**overrides):
    base = {"FLASK_ENV": "testing", "SECRET_KEY": "x"}
    base.update(overrides)
    return base


def test_extra_ytdlp_args_defaults_empty():
    config = Config.from_env(_env())
    assert config.extra_ytdlp_args == ()


def test_extra_ytdlp_args_parsed_shell_style():
    config = Config.from_env(_env(EXTRA_YTDLP_ARGS='--extractor-args "tiktok:app_name=trill"'))
    assert config.extra_ytdlp_args == ("--extractor-args", "tiktok:app_name=trill")


def test_extra_ytdlp_args_rejects_unbalanced_quotes():
    with pytest.raises(ConfigurationError):
        Config.from_env(_env(EXTRA_YTDLP_ARGS='--extractor-args "unterminated'))


def test_check_ytdlp_updates_defaults_true():
    assert Config.from_env(_env()).check_ytdlp_updates is True


def test_check_ytdlp_updates_can_be_disabled():
    assert Config.from_env(_env(CHECK_YTDLP_UPDATES="false")).check_ytdlp_updates is False


def test_update_check_never_raises_when_pypi_unreachable(monkeypatch):
    from app.services import update_check

    def boom(*a, **k):
        raise OSError("network unreachable")

    monkeypatch.setattr(update_check.urllib.request, "urlopen", boom)
    update_check.check_ytdlp_current()  # must not raise


def test_update_check_warns_when_outdated(monkeypatch, caplog):
    from app.services import update_check
    import json
    import io

    class FakeResp(io.BytesIO):
        def __enter__(self): return self
        def __exit__(self, *a): return False

    monkeypatch.setattr(update_check, "version", lambda name: "2020.1.1")
    monkeypatch.setattr(update_check.urllib.request, "urlopen",
                        lambda *a, **k: FakeResp(json.dumps({"info": {"version": "2099.1.1"}}).encode()))
    with caplog.at_level("WARNING", logger="clipfetch.startup"):
        update_check.check_ytdlp_current()
    assert any("2099.1.1" in r.message for r in caplog.records)


def test_impersonation_check_passes_when_curl_cffi_installed(caplog):
    from app.services import update_check
    with caplog.at_level("INFO", logger="clipfetch.startup"):
        update_check.check_impersonation_available()
    assert any("available" in r.message for r in caplog.records)
    assert not any(r.levelname == "WARNING" for r in caplog.records)


def test_impersonation_check_warns_when_curl_cffi_missing(monkeypatch, caplog):
    import builtins
    from app.services import update_check

    real_import = builtins.__import__

    def fake_import(name, *a, **k):
        if name == "curl_cffi":
            raise ImportError("no module named curl_cffi")
        return real_import(name, *a, **k)

    monkeypatch.setattr(builtins, "__import__", fake_import)
    with caplog.at_level("WARNING", logger="clipfetch.startup"):
        update_check.check_impersonation_available()
    assert any("curl_cffi" in r.message for r in caplog.records)
