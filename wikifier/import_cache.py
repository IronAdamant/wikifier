"""
Backward compatibility shim for wikifier.import_cache.

This module maintains 100% API compatibility with code that imports from
wikifier.import_cache, while the actual implementation has moved to the
wikifier.cache package for better organization.

All imports are transparently redirected to wikifier.cache.
"""

from .cache import *

# Explicitly re-export for static analysis tools
__all__ = [
    'load_cache', 'save_cache', 'load_mtime_index',
    'get_file_data', 'update_file_data', 'get_mtime', 'compute_file_content_hash',
    'build_dependency_graph', 'get_reverse_dependencies', 'set_reverse_dependencies',
    'maintain_reverse_dependencies_for_source', 'rebuild_reverse_dependencies',
    'get_reverse_dependency_stats', 'graph_signature', 'reverse_dependency_signature',
    'get_reverse_signature', 'set_reverse_signature', 'get_graph_signature',
    'set_graph_signature', 'compute_cycles', 'get_cycles', 'set_cycles',
    'compute_graph_integrity', 'set_graph_integrity', 'get_cycles_reuse_stats',
    'build_graph_with_edge_metadata', 'compute_acs_summary', 'get_acs_summary',
    'set_acs_summary', 'ensure_acs_summary_persisted', 'build_map_coverage',
    'classify_edge_agent_signal', 'compute_cycle_analyses', 'get_cycle_analyses',
    'set_cycle_analyses', 'compute_files_needing_reparse', 'get_barrel_resolutions',
    'get_barrel_file_index', 'set_barrel_resolutions', 'set_barrel_file_index',
    'invalidate_stale_barrel_entries', 'get_barrel_invalidation_reports',
    'get_barrel_cache_summary', 'append_barrel_invalidation_log',
    'get_resolution_diagnostics', 'ensure_diagnostics_aggregate',
    'get_unresolved_imports', 'get_low_confidence_edges', 'prune_barrel_resolutions',
    'generate_update_events', 'run_update_stream',
    'NODE_IDENTITY_VERSION_V0', 'NODE_IDENTITY_VERSION_V1', 'CACHE_FILE',
]
