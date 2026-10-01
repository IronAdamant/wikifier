"""Import cache + graph intelligence (also importable as ``wikifier.import_cache``).

Modules:
  io           load/save the cache dict (SQLite store in ``wikifier.cache_store``)
  files        per-file entries, mtimes, content hashes, dirty detection
  graph        forward adjacency, reverse index, Tarjan SCC, signatures
  cycles       cycle detection + impact analysis / breaking recommendations
  acs          agent confidence summary + map coverage
  barrel       barrel re-export cache persistence, invalidation, pruning
  diagnostics  unresolved / low-confidence aggregates

Reserved top-level keys start with ``_`` (``_cycles``, ``_acs_summary``,
``_barrel_resolutions``, ``_reverse_dependencies``, …); everything else is a
project-relative file path.
"""

from ..contracts import NODE_IDENTITY_VERSION_V0, NODE_IDENTITY_VERSION_V1  # noqa: F401
from .io import CACHE_FILE, load_cache, load_mtime_index, save_cache  # noqa: F401
from .files import (  # noqa: F401
    compute_file_content_hash,
    compute_files_needing_reparse,
    get_file_data,
    get_mtime,
    get_mtime_ns,
    update_file_data,
)
from .graph import (  # noqa: F401
    build_dependency_graph,
    build_graph_with_edge_metadata,
    get_graph_signature,
    get_reverse_dependencies,
    get_reverse_dependency_stats,
    get_reverse_signature,
    graph_signature,
    maintain_reverse_dependencies_for_source,
    rebuild_reverse_dependencies,
    remove_file_from_graph,
    reverse_dependency_signature,
    set_graph_signature,
    set_reverse_dependencies,
    set_reverse_signature,
)
from .cycles import (  # noqa: F401
    compute_cycle_analyses,
    compute_cycles,
    compute_graph_integrity,
    get_cycle_analyses,
    get_cycles,
    get_cycles_reuse_stats,
    set_cycle_analyses,
    set_cycles,
    set_graph_integrity,
)
from .acs import (  # noqa: F401
    _edge_is_dynamic_literal_noise,
    _edge_is_external_noise,
    _edge_is_non_actionable_noise,
    build_map_coverage,
    classify_edge_agent_signal,
    compute_acs_summary,
    ensure_acs_summary_persisted,
    get_acs_summary,
    set_acs_summary,
)
from .barrel import (  # noqa: F401
    append_barrel_invalidation_log,
    get_barrel_cache_summary,
    get_barrel_file_index,
    get_barrel_invalidation_reports,
    get_barrel_resolutions,
    invalidate_stale_barrel_entries,
    prune_barrel_resolutions,
    set_barrel_file_index,
    set_barrel_resolutions,
)
from .diagnostics import (  # noqa: F401
    ensure_diagnostics_aggregate,
    get_low_confidence_edges,
    get_resolution_diagnostics,
    get_unresolved_imports,
)

__all__ = [
    "load_cache", "save_cache", "load_mtime_index", "CACHE_FILE",
    "get_file_data", "update_file_data", "get_mtime", "get_mtime_ns",
    "compute_file_content_hash", "compute_files_needing_reparse",
    "build_dependency_graph", "build_graph_with_edge_metadata",
    "get_reverse_dependencies", "set_reverse_dependencies",
    "maintain_reverse_dependencies_for_source", "rebuild_reverse_dependencies",
    "remove_file_from_graph", "get_reverse_dependency_stats",
    "graph_signature", "reverse_dependency_signature",
    "get_reverse_signature", "set_reverse_signature",
    "get_graph_signature", "set_graph_signature",
    "compute_cycles", "get_cycles", "set_cycles", "get_cycles_reuse_stats",
    "compute_graph_integrity", "set_graph_integrity",
    "compute_cycle_analyses", "get_cycle_analyses", "set_cycle_analyses",
    "compute_acs_summary", "get_acs_summary", "set_acs_summary",
    "ensure_acs_summary_persisted", "build_map_coverage", "classify_edge_agent_signal",
    "get_barrel_resolutions", "get_barrel_file_index",
    "set_barrel_resolutions", "set_barrel_file_index",
    "invalidate_stale_barrel_entries", "get_barrel_invalidation_reports",
    "get_barrel_cache_summary", "append_barrel_invalidation_log", "prune_barrel_resolutions",
    "get_resolution_diagnostics", "ensure_diagnostics_aggregate",
    "get_unresolved_imports", "get_low_confidence_edges",
    "NODE_IDENTITY_VERSION_V0", "NODE_IDENTITY_VERSION_V1",
    "_edge_is_dynamic_literal_noise", "_edge_is_external_noise", "_edge_is_non_actionable_noise",
]
