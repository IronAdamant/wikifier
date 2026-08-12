"""
BREE (Barrel Re-Export Engine) package - modularized barrel expansion.

Main entry point: follow_barrel_chain, reset_bree_engine
"""

# Re-export all functions for backward compatibility
from ._bree import *

__all__ = [
    'follow_barrel_chain',
    'reset_bree_engine',
    'get_barrel_cache_stats',
    'get_bree_engine',
    'save_bree_barrel_cache',
]
