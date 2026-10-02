"""Shared extension instances, created without an app so blueprints can import them."""
from __future__ import annotations

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(get_remote_address, storage_uri="memory://", default_limits=[],
                  headers_enabled=True)
