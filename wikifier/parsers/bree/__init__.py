"""
BREE (Barrel Re-Export Engine) package - modularized barrel expansion.

Main entry point: follow_barrel_chain, reset_bree_engine
"""

from ._bree import *  # noqa: F401,F403 — public BREE surface
from ._bree import (  # noqa: F401
    flush_barrel_cache,
    get_bree_engine,
    reset_bree_engine,
)


def follow_barrel_chain(*args, **kwargs):
    """Public alias for BREE engine.expand_chain (advertised in __all__)."""
    return get_bree_engine().expand_chain(*args, **kwargs)


def get_barrel_cache_stats():
    """Best-effort cache stats; empty dict when the engine has no stats hook."""
    try:
        eng = get_bree_engine()
        for name in ("cache_stats", "stats", "get_stats"):
            fn = getattr(eng, name, None)
            if callable(fn):
                return fn() or {}
    except Exception:
        pass
    return {}


__all__ = [
    'follow_barrel_chain',
    'reset_bree_engine',
    'get_barrel_cache_stats',
    'get_bree_engine',
    'flush_barrel_cache',
]
