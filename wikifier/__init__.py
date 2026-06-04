"""
Wikifier Python Package

Provides the core Python components for Wikifier, including:
- Import parsers (Python + JavaScript/TypeScript)
- MCP Server
- Health Matrix (scalable implementation)
- Python-primary Library API (Workstream E): direct callable core ops
  for agents without shell (health, record_change, check_changes,
  suggest_next_actions, update_maps, etc.). See cli.py + design in
  m2-full-closure-longterm-scalable-plan.md.

Clean public API note (post-audit): `from wikifier import health` yields the
convenience function (protocol-preferred). Submodule internals via
`from wikifier.health import upsert_entry, ...` (dotted form guaranteed).
See Agent 6 resumption notes in the long-term plan for rigorous contracts.
"""

from . import parsers
from . import mcp
from . import health  # Health matrix module (submodule import always available via "from wikifier.health import ..." even with flat func binding below)
from . import locking
from . import import_cache
from . import resolution  # Robust Path Normalization Layer (Limitation #3 / Gap #1)
from . import diagnostics  # Failure Transparency & Diagnostics Layer (Limitation #5 / Gap #1) - schema, aggregates, get_resolution_diagnostics support
# Phase 5e (66): __init__ re-exports + docs now note health/suggest/import_cache summaries (format=summary default for 20k+ creative O(k) ACS/CIABRE/barrel; additive per 48/58/47).

# Gap #1 External / Packaged: unified discovery helper (CLI + MCP + shell mirror) for reliable
# PROJECT_ROOT on external monorepos after `pip install wikifier`. Primary entry for Python consumers.
# Wave 2: + run_full_update (Python-primary sketch for update-maps heavy path)
from .cli import (
    discover_project_root,
    run_full_update,
    # Workstream E library surface (Python-primary, mandatory workflow)
    check_changes,
    record_change,
    record_deletion,
    mark_green,
    suggest_next_actions,
    update_maps,
    health,  # Flat convenience func (delegates to health module + adds scoping/acs). Binds "health" name at package level.
)

# Pre-Wave 0: Shared contracts (FROZEN foundation for all Gap #1 phases)
from . import contracts
from .contracts import (
    AnalysisTraceEntry,
    ConditionalAnalysis,
    DynamicAnalysis,
    ResolutionMetadata,
    encode_v1_payload,
    decode_v1_payload,
    pack_cdia_v1,
    unpack_cdia_v1,
    parse_pipeline_line,
    RICH_KEYS,
    RESERVED_TOP_LEVEL_KEYS,
    NODE_IDENTITY_VERSION_V0,
    NODE_IDENTITY_VERSION_V1,
    get_contracts_info,
    # R2: canonical ACS for consistent high-quality explanations + scores
    compute_acs_confidence,
)

__version__ = "4.1.0"
