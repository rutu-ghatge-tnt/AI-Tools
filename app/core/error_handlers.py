# app/core/error_handlers.py

from __future__ import annotations
import logging
import traceback
from typing import Any, Dict

logger = logging.getLogger(__name__)

def sanitize_error_message(err: Exception, *, expose: bool = False) -> str:
    """
    Returns a user-safe error message.
    - expose=False: generic message (production)
    - expose=True : includes actual error text (debug)
    """
    if expose:
        return f"{type(err).__name__}: {err}"
    return "Something went wrong. Please try again."

def build_error_payload(err: Exception, *, expose: bool = False) -> Dict[str, Any]:
    payload: Dict[str, Any] = {
        "success": False,
        "message": sanitize_error_message(err, expose=expose),
    }
    if expose:
        payload["trace"] = traceback.format_exc()
    return payload
