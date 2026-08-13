"""Import cache + graph intelligence (agent-first).

Public API is backward compatible with wikifier.import_cache.

Implementation map:
  io.py           load/save / mtime index
  files.py        file entries, content hash, dirty set
  graph.py        reverse deps + graph signatures
  cycles.py       Tarjan SCC + CIABRE
  acs.py          ACS v1.3 + map coverage
  barrel.py       BRC persist + invalidation
  diagnostics.py  unresolved / low-conf aggregates
  streaming.py    optional event facade
  _core.py        remaining graph/cycle/ACS/barrel bodies
"""

from .io import (  # noqa: F401
    CACHE_FILE,
    load_cache,
    save_cache,
    load_mtime_index,
)
from .files import (  # noqa: F401
    get_file_data,
    update_file_data,
    get_mtime,
    compute_file_content_hash,
    compute_files_needing_reparse,
)
from .graph import (  # noqa: F401
    build_dependency_graph,
    get_reverse_dependencies,
    set_reverse_dependencies,
    maintain_reverse_dependencies_for_source,
    rebuild_reverse_dependencies,
    get_reverse_dependency_stats,
    graph_signature,
    reverse_dependency_signature,
    get_reverse_signature,
    set_reverse_signature,
    get_graph_signature,
    set_graph_signature,
    compute_graph_integrity,
    set_graph_integrity,
    build_graph_with_edge_metadata,
)
from .cycles import (  # noqa: F401
    compute_cycles,
    get_cycles,
    set_cycles,
    get_cycles_reuse_stats,
    compute_cycle_analyses,
    get_cycle_analyses,
    set_cycle_analyses,
)
from .acs import (  # noqa: F401
    compute_acs_summary,
    get_acs_summary,
    set_acs_summary,
    ensure_acs_summary_persisted,
    build_map_coverage,
    classify_edge_agent_signal,
    _edge_is_dynamic_literal_noise,
    _edge_is_external_noise,
    _edge_is_non_actionable_noise,
)
from .barrel import (  # noqa: F401
    get_barrel_resolutions,
    get_barrel_file_index,
    set_barrel_resolutions,
    set_barrel_file_index,
    invalidate_stale_barrel_entries,
    get_barrel_invalidation_reports,
    get_barrel_cache_summary,
    append_barrel_invalidation_log,
    prune_barrel_resolutions,
)
from .diagnostics import (  # noqa: F401
    get_resolution_diagnostics,
    ensure_diagnostics_aggregate,
    get_unresolved_imports,
    get_low_confidence_edges,
)
from .streaming import generate_update_events, run_update_stream  # noqa: F401

try:
    from ..contracts import NODE_IDENTITY_VERSION_V0, NODE_IDENTITY_VERSION_V1
except Exception:
    NODE_IDENTITY_VERSION_V0 = "v0"
    NODE_IDENTITY_VERSION_V1 = "v1"

__all__ = [
    "load_cache", "save_cache", "load_mtime_index",
    "get_file_data", "update_file_data", "get_mtime", "compute_file_content_hash",
    "compute_files_needing_reparse",
    "build_dependency_graph", "get_reverse_dependencies", "set_reverse_dependencies",
    "maintain_reverse_dependencies_for_source", "rebuild_reverse_dependencies",
    "get_reverse_dependency_stats", "graph_signature", "reverse_dependency_signature",
    "get_reverse_signature", "set_reverse_signature", "get_graph_signature",
    "set_graph_signature", "compute_graph_integrity", "set_graph_integrity",
    "compute_cycles", "get_cycles", "set_cycles", "get_cycles_reuse_stats",
    "build_graph_with_edge_metadata", "compute_acs_summary", "get_acs_summary",
    "set_acs_summary", "ensure_acs_summary_persisted", "build_map_coverage",
    "classify_edge_agent_signal", "compute_cycle_analyses", "get_cycle_analyses",
    "set_cycle_analyses", "get_barrel_resolutions", "get_barrel_file_index",
    "set_barrel_resolutions", "set_barrel_file_index",
    "invalidate_stale_barrel_entries", "get_barrel_invalidation_reports",
    "get_barrel_cache_summary", "append_barrel_invalidation_log",
    "get_resolution_diagnostics", "ensure_diagnostics_aggregate",
    "get_unresolved_imports", "get_low_confidence_edges", "prune_barrel_resolutions",
    "generate_update_events", "run_update_stream",
    "NODE_IDENTITY_VERSION_V0", "NODE_IDENTITY_VERSION_V1", "CACHE_FILE",
    "_edge_is_dynamic_literal_noise", "_edge_is_external_noise",
    "_edge_is_non_actionable_noise",
]
