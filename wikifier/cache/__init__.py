"""
Wikifier cache package - modularized import cache and graph intelligence.

This package provides the core caching, graph analysis, cycle detection,
and dependency intelligence for the Wikifier project.

Public API (backward compatible with wikifier.import_cache):
- Cache I/O: load_cache, save_cache, load_mtime_index  
- File operations: get_file_data, update_file_data, get_mtime, compute_file_content_hash
- Graph operations: build_dependency_graph, get/set_reverse_dependencies, graph_signature
- Cycle detection: compute_cycles, get/set_cycles, CIABRE analysis
- ACS (Agent Confidence Scoring): compute_acs_summary, classify_edge_agent_signal
- Barrel operations: invalidate_stale_barrel_entries, get_barrel_reports
- Diagnostics: get_resolution_diagnostics, get_unresolved_imports
- Streaming: generate_update_events, run_update_stream

All functions maintain backward compatibility with the original wikifier.import_cache module.
"""

# Re-export everything from the monolithic implementation for now
# This maintains 100% backward compatibility while allowing gradual migration
from ..import_cache_impl import *

# Explicitly import private functions used by tests for backward compatibility
from ..import_cache_impl import (
    _edge_is_dynamic_literal_noise,
    _edge_is_external_noise,
    _edge_is_non_actionable_noise,
)

__all__ = [
    # I/O operations
    'load_cache',
    'save_cache', 
    'load_mtime_index',
    # File operations
    'get_file_data',
    'update_file_data',
    'get_mtime',
    'compute_file_content_hash',
    'compute_files_needing_reparse',
    # Graph operations
    'build_dependency_graph',
    'get_reverse_dependencies',
    'set_reverse_dependencies',
    'maintain_reverse_dependencies_for_source',
    'rebuild_reverse_dependencies',
    'get_reverse_dependency_stats',
    'graph_signature',
    'reverse_dependency_signature',
    'get_reverse_signature',
    'set_reverse_signature',
    'get_graph_signature',
    'set_graph_signature',
    'compute_graph_integrity',
    'set_graph_integrity',
    # Cycle detection
    'compute_cycles',
    'get_cycles',
    'set_cycles',
    'get_cycles_reuse_stats',
    'build_graph_with_edge_metadata',
    'compute_cycle_analyses',
    'get_cycle_analyses',
    'set_cycle_analyses',
    # ACS
    'compute_acs_summary',
    'get_acs_summary',
    'set_acs_summary',
    'ensure_acs_summary_persisted',
    'build_map_coverage',
    'classify_edge_agent_signal',
    # Barrel operations
    'get_barrel_resolutions',
    'get_barrel_file_index',
    'set_barrel_resolutions',
    'set_barrel_file_index',
    'invalidate_stale_barrel_entries',
    'get_barrel_invalidation_reports',
    'get_barrel_cache_summary',
    'append_barrel_invalidation_log',
    'prune_barrel_resolutions',
    # Diagnostics
    'get_resolution_diagnostics',
    'ensure_diagnostics_aggregate',
    'get_unresolved_imports',
    'get_low_confidence_edges',
    # Streaming
    'generate_update_events',
    'run_update_stream',
    # Constants
    'NODE_IDENTITY_VERSION_V0',
    'NODE_IDENTITY_VERSION_V1',
    'CACHE_FILE',
    # Private functions used by tests (for backward compatibility)
    '_edge_is_dynamic_literal_noise',
    '_edge_is_external_noise',
    '_edge_is_non_actionable_noise',
]
