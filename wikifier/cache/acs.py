"""ACS v1.3 — agent confidence scoring + map coverage."""
from ._core import (
    classify_edge_agent_signal,
    compute_acs_summary,
    get_acs_summary,
    set_acs_summary,
    ensure_acs_summary_persisted,
    build_map_coverage,
    _edge_is_dynamic_literal_noise,
    _edge_is_external_noise,
    _edge_is_non_actionable_noise,
)
