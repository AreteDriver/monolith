"""Lightweight in-memory error tracking for unhandled exceptions.

Captures the last 100 unhandled errors into a ring buffer (deque).
Exposes via GET /api/admin/errors (admin-gated via X-Admin-Key header).
"""

import time
import traceback
from collections import deque
from typing import Any

from fastapi import APIRouter, HTTPException, Request

router = APIRouter()

# Ring buffer — last 100 errors, no database, no external deps
_error_buffer: deque[dict[str, Any]] = deque(maxlen=100)


def capture_error(request: Request, exc: Exception) -> None:
    """Record an unhandled exception into the ring buffer."""
    tb_lines = traceback.format_exception(type(exc), exc, exc.__traceback__)
    _error_buffer.append(
        {
            "timestamp": int(time.time()),
            "path": str(request.url.path),
            "method": request.method,
            "error_type": type(exc).__name__,
            "message": str(exc),
            "traceback": "".join(tb_lines[-5:]),
        }
    )


def get_errors() -> list[dict[str, Any]]:
    """Return all captured errors (most recent last)."""
    return list(_error_buffer)


@router.get("/admin/errors")
async def get_admin_errors(request: Request):
    """Recent unhandled exceptions — admin only (X-Admin-Key header)."""
    settings = request.app.state.settings
    admin_key = getattr(settings, "admin_key", "")
    if not admin_key:
        raise HTTPException(403, "Admin endpoint not configured.")
    provided = request.headers.get("X-Admin-Key", "")
    if not provided or provided != admin_key:
        raise HTTPException(403, "Invalid admin key.")
    errors = get_errors()
    return {"count": len(errors), "errors": errors}
