"""
JavaScript/TypeScript parser package - modularized import analysis.

Main entry point: parse_javascript_imports(path)
"""

# Re-export main function and utilities for backward compatibility
from ._parser import (
    parse_javascript_imports,
    _clear_parse_cache,
    _clear_reexport_cache,
    _clear_package_marker_cache,
)

__all__ = [
    'parse_javascript_imports',
    '_clear_parse_cache',
    '_clear_reexport_cache',
    '_clear_package_marker_cache',
]
