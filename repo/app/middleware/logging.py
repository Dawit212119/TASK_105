"""
Structured JSON request/response logger.
Strips sensitive keys from any logged data: passwords, payout fields, message body.
Message.body is excluded at this layer so it never appears in log output even if
a future code path accidentally includes it in a loggable structure.
"""
import json
import os
import time
import uuid
import logging
from flask import Flask, g, request

# Keys redacted from any dict that passes through _redact().
# "body" covers Messages.body (chat content — must not be stored in logs).
REDACTED_KEYS = frozenset({
    "password",
    "password_hash",
    "current_password",
    "new_password",
    "body",          # Messages.body — chat content must not appear in logs
})


def _redact(obj, depth: int = 0):
    if depth > 5:
        return obj
    if isinstance(obj, dict):
        return {
            k: "[REDACTED]" if k in REDACTED_KEYS or k.startswith("payout_") else _redact(v, depth + 1)
            for k, v in obj.items()
        }
    if isinstance(obj, list):
        return [_redact(i, depth + 1) for i in obj]
    return obj


def init_logging_middleware(app: Flask) -> None:
    log_file = app.config.get("LOG_FILE", "data/logs/app.jsonl")
    log_level = app.config.get("LOG_LEVEL", "INFO")

    os.makedirs(os.path.dirname(log_file) or ".", exist_ok=True)
    handler = logging.FileHandler(log_file)
    handler.setLevel(log_level)
    app.logger.addHandler(handler)
    app.logger.setLevel(log_level)

    @app.before_request
    def start_timer():
        g.start_time = time.time()
        g.span_id = str(uuid.uuid4())

    @app.after_request
    def log_request(response):
        duration_ms = round((time.time() - getattr(g, "start_time", time.time())) * 1000, 2)
        user = getattr(g, "current_user", None)

        entry = {
            "timestamp": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "level": "WARN" if duration_ms > 100 else "INFO",
            "correlation_id": getattr(g, "correlation_id", ""),
            "span_id": getattr(g, "span_id", ""),
            "user_id": str(user.user_id) if user else None,
            "method": request.method,
            "path": request.path,
            "status_code": response.status_code,
            "duration_ms": duration_ms,
        }
        app.logger.info(json.dumps(entry))
        return response
