"""In-process MCP wall-clock cap (stdlib; no FastMCP import)."""
from __future__ import annotations

import os
import threading
from typing import Any, Dict, Optional

MCP_INPROCESS_DEADLINE_S = float(os.environ.get("WIKIFIER_MCP_DEADLINE_S", "60") or "60")
MCP_ATTENTION_LIMIT = int(os.environ.get("WIKIFIER_MCP_ATTENTION_LIMIT", "200") or "200")


def call_with_deadline(fn, *args, timeout_s: Optional[float] = None, **kwargs):
    """Run fn with a wall-clock cap. timeout_s<=0 forces a timeout for tests."""
    t = MCP_INPROCESS_DEADLINE_S if timeout_s is None else timeout_s
    try:
        t = float(t)
    except (TypeError, ValueError):
        t = MCP_INPROCESS_DEADLINE_S
    if t <= 0:
        return {
            "success": False,
            "timed_out": True,
            "error": "MCP in-process deadline exceeded",
        }
    box: Dict[str, Any] = {}

    def _target():
        try:
            box["r"] = fn(*args, **kwargs)
        except BaseException as e:
            box["e"] = e

    thr = threading.Thread(target=_target, daemon=True)
    thr.start()
    thr.join(t)
    if thr.is_alive():
        return {
            "success": False,
            "timed_out": True,
            "error": "MCP in-process deadline exceeded",
        }
    if "e" in box:
        raise box["e"]
    return box.get("r")
