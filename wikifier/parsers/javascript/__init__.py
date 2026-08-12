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
    # Also export internal functions used by python.py for dynamic import detection
    _extract_balanced_argument,
    _extract_candidate_literals,
    _apply_dynamic_registry,
    _analyze_dynamic_specifier,
)

__all__ = [
    'parse_javascript_imports',
    '_clear_parse_cache',
    '_clear_reexport_cache',
    '_clear_package_marker_cache',
    '_extract_balanced_argument',
    '_extract_candidate_literals',
    '_apply_dynamic_registry',
    '_analyze_dynamic_specifier',
]
