"""
Wikifier Python Package

Zero-dependency, agent-to-agent codebase wiki. Provides:

- Import parsers (Python + JavaScript/TypeScript) under `wikifier.parsers`
- Health matrix tracking (`wikifier.health`)
- Persistent import/dependency cache with cycle + confidence analysis
  (`wikifier.import_cache`)
- Central path/specifier resolution (`wikifier.resolution`)
- Resolution failure diagnostics (`wikifier.diagnostics`)
- Optional MCP server (`wikifier.mcp`; requires `pip install wikifier[mcp]`)

The flat library API below (check_changes, record_change, mark_green,
health, update_maps, ...) is the preferred surface for agents calling
Wikifier directly from Python.

**Health import hygiene (G5):** `from wikifier import health` is the *convenience
function* (cli). The real module is always `importlib.import_module("wikifier.health")`
or `from wikifier.health import upsert_entry, get_summary, ...`. Prefer
`wikifier.health_module` (alias below) over `import wikifier.health as …`, which
binds the function under CPython because the package attribute is shadowed.
"""

from . import parsers
from . import mcp  # exposes wikifier.mcp.mcp (None when the optional extra is absent)
from . import health as health_module  # submodule — keep this name for agents/tools
from . import locking
from . import import_cache
from . import resolution
from . import diagnostics

# Unified project-root discovery and the Python-primary library surface.
# These are the canonical entry points for agents (no shell required).
from .cli import (
    discover_project_root,
    run_full_update,
    check_changes,
    record_change,
    record_deletion,
    mark_green,
    suggest_next_actions,
    update_maps,
    health,  # flat convenience func (delegates to the health module + adds scoping)
    session_bootstrap,
    prepare_edit,
    search_journal,
    why_file,
)
from . import agent_loop

# Re-export module under a non-shadowed name (G5). sys.modules['wikifier.health']
# remains the real module; package attribute `health` is intentionally the function.
import sys as _sys
if "wikifier.health" not in _sys.modules:
    _sys.modules["wikifier.health"] = health_module

# Shared frozen data contracts (single source of truth for shapes used by
# parsers, cache, MCP, and diagnostics).
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
    compute_acs_confidence,
)

__version__ = "4.6.1"
