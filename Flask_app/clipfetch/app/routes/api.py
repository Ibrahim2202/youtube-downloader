"""JSON API: analyze a URL, start a download job, poll status, fetch the file."""
from __future__ import annotations

import logging
import time
import uuid

from flask import Blueprint, current_app, g, jsonify, request, send_file

from ..errors import AppError, InvalidRequest, JobNotFound
from ..utils.helpers import is_valid_job_id
from ..utils.logging import log_event
from ..extensions import limiter

bp = Blueprint("api", __name__, url_prefix="/api")
logger = logging.getLogger("clipfetch.api")


@bp.before_app_request
def _assign_request_id() -> None:
    g.request_id = uuid.uuid4().hex[:12]


def _services():
    return current_app.extensions["clipfetch"]


def _json_body() -> dict:
    if not request.is_json:
        raise InvalidRequest("body must be application/json")
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        raise InvalidRequest("body must be a JSON object")
    return body


@bp.errorhandler(AppError)
def _handle_app_error(exc: AppError):
    level = logging.WARNING if exc.http_status < 500 else logging.ERROR
    log_event(logger, level, "request failed", request_id=g.get("request_id"),
              operation=request.endpoint, result="failed", error_category=exc.code,
              detail=exc.detail)
    return jsonify(success=False, error=exc.to_dict()), exc.http_status


@bp.errorhandler(413)
def _handle_too_large(_exc):
    return jsonify(success=False, error={"code": "request_too_large", "retryable": False,
                                         "message": "That request is too large."}), 413


@bp.post("/info")
@limiter.limit(lambda: _services().config.rate_limit_info)
def info():
    services = _services()
    target = services.downloader.validate_url(_json_body().get("url"))
    started = time.monotonic()
    media = services.downloader.extract_info(target)
    log_event(logger, logging.INFO, "info lookup", request_id=g.request_id, platform=target.platform,
              operation="info", duration_ms=int((time.monotonic() - started) * 1000), result="success")
    return jsonify(success=True, **media.to_dict())


@bp.post("/download")
@limiter.limit(lambda: _services().config.rate_limit_download)
def start_download():
    services = _services()
    body = _json_body()
    target = services.downloader.validate_url(body.get("url"))
    preset = services.validate_preset(body.get("format_id"), services.config.max_height)
    job = services.jobs.submit(target, preset)
    log_event(logger, logging.INFO, "job queued", request_id=g.request_id, job_id=job.id,
              platform=target.platform, operation="download", result="queued")
    return jsonify(success=True, job_id=job.id, status=job.status.value), 202


@bp.get("/download/<job_id>")
@limiter.limit(lambda: _services().config.rate_limit_status)
def job_status(job_id: str):
    if not is_valid_job_id(job_id):
        raise JobNotFound(job_id)
    job = _services().jobs.get(job_id)
    return jsonify(success=True, **_services().jobs.snapshot(job))


@bp.get("/download/<job_id>/file")
def job_file(job_id: str):
    if not is_valid_job_id(job_id):
        raise JobNotFound(job_id)
    path, file_name = _services().jobs.file_for(job_id)
    return send_file(path, as_attachment=True, download_name=file_name, conditional=True)


@bp.get("/health")
def health():
    services = _services()
    return jsonify(success=True, ffmpeg=services.downloader.ffmpeg_available,
                   active_jobs=services.jobs.active_count(),
                   max_concurrent_jobs=services.config.max_concurrent_jobs)
