"""Gunicorn config. One process, several threads: job state lives in-process (see
app/services/jobs.py), so running >1 worker would split that state and jobs started on
one worker would 404 on another. Scale the thread count and MAX_CONCURRENT_JOBS instead.
"""
import multiprocessing
import os

bind = f"0.0.0.0:{os.environ.get('PORT', '8000')}"
workers = 1
threads = max(4, multiprocessing.cpu_count() * 2)
worker_class = "gthread"
timeout = int(os.environ.get("DOWNLOAD_TIMEOUT", "600")) + 30
graceful_timeout = 30
keepalive = 5
max_requests = 500
max_requests_jitter = 50
accesslog = "-"
errorlog = "-"
