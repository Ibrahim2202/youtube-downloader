"""Application factory. Wires config, services and blueprints together."""
from __future__ import annotations

import logging
from dataclasses import dataclass

from flask import Flask, jsonify, render_template, request
from werkzeug.middleware.proxy_fix import ProxyFix

from .config import Config
from .errors import AppError, ConfigurationError
from .extensions import limiter
from .services.cleanup import CleanupService, wipe_directory
from .services.downloader import DownloaderService
from .services.ffmpeg import check_ffmpeg
from .services.jobs import JobManager
from .services.validation import validate_preset
from .utils.logging import setup_logging

logger = logging.getLogger("clipfetch")


@dataclass
class Services:
    config: Config
    downloader: DownloaderService
    jobs: JobManager
    cleanup: CleanupService

    @staticmethod
    def validate_preset(value: object, max_height: int) -> str:
        return validate_preset(value, max_height)


def create_app(config: Config | None = None) -> Flask:
    config = config or Config.from_env()
    setup_logging(config.log_level, config.log_json)

    for directory in (config.download_dir, config.temp_dir):
        directory.mkdir(parents=True, exist_ok=True)
    if config.env != "testing":
        removed = wipe_directory(config.temp_dir) + wipe_directory(config.download_dir)
        if removed:
            logger.info("startup: wiped %d orphaned job artifact(s)", removed)

    ffmpeg = None
    try:
        ffmpeg = check_ffmpeg(config.ffmpeg_path)
        logger.info("ffmpeg ready: %s", ffmpeg.version)
    except AppError as exc:
        if config.require_ffmpeg:
            raise ConfigurationError(str(exc)) from exc
        logger.warning("starting WITHOUT ffmpeg (REQUIRE_FFMPEG=false): %s", exc.detail)

    if config.check_ytdlp_updates and config.env != "testing":
        from .services.update_check import check_impersonation_available, check_ytdlp_current
        check_ytdlp_current()
        check_impersonation_available()

    from .config import BASE_DIR
    app = Flask(__name__, template_folder=str(BASE_DIR / "templates"),
               static_folder=str(BASE_DIR / "static"))
    app.config.update(SECRET_KEY=config.secret_key, MAX_CONTENT_LENGTH=config.max_request_bytes,
                      JSON_SORT_KEYS=False)
    if config.trusted_proxies:
        app.wsgi_app = ProxyFix(app.wsgi_app, x_for=config.trusted_proxies,
                                x_proto=config.trusted_proxies, x_host=config.trusted_proxies)

    downloader = DownloaderService(config, ffmpeg)
    jobs = JobManager(config, downloader)
    services = Services(config=config, downloader=downloader, jobs=jobs,
                        cleanup=CleanupService(config, jobs))
    app.extensions["clipfetch"] = services

    limiter.init_app(app)

    from .routes.api import bp as api_bp
    from .routes.pages import bp as pages_bp
    app.register_blueprint(pages_bp)
    app.register_blueprint(api_bp)

    @app.errorhandler(404)
    def not_found(_exc):
        if request.path.startswith("/api/"):
            return jsonify(success=False, error={"code": "not_found", "retryable": False,
                                                 "message": "Not found."}), 404
        return render_template("index.html"), 404

    @app.errorhandler(500)
    def server_error(_exc):
        logger.exception("unhandled exception")
        return jsonify(success=False, error={"code": "internal_error", "retryable": False,
                                             "message": "Something went wrong on our side."}), 500

    if config.env != "testing":
        services.cleanup.start()

    return app
