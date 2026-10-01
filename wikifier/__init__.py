"""
Wikifier — zero-dependency, agent-to-agent codebase wiki.

Library surface (preferred for agents calling from Python)::

    from wikifier import session_bootstrap, check_changes, record_change, mark_green
    from wikifier import update_maps, prepare_edit, suggest_next_actions, health

Subpackages: ``wikifier.parsers`` (import parsers), ``wikifier.health``
(health matrix module; also ``wikifier.health_module``), ``wikifier.import_cache``
(dependency cache + graph intelligence), ``wikifier.resolution`` (path
resolution), ``wikifier.mcp`` (optional MCP server, ``pip install wikifier[mcp]``).

``wikifier.health`` as an *attribute* is the ``health()`` convenience function;
``import wikifier.health`` / ``importlib.import_module("wikifier.health")``
give the module (registered below so both spellings work).
"""

__version__ = "4.7.0"

import sys as _sys

from . import parsers  # noqa: F401
from . import health_pkg as health_module
from . import locking  # noqa: F401
from . import import_cache  # noqa: F401
from . import resolution  # noqa: F401
from . import diagnostics  # noqa: F401
from . import contracts  # noqa: F401
from .api import (  # noqa: F401
    cache_status,
    check_changes,
    cycles_report,
    discover_project_root,
    get_dependencies,
    get_dependents,
    heal_stubs,
    health,
    init_project,
    list_core_tools,
    list_paths,
    mark_green,
    prepare_edit,
    record_change,
    record_changes,
    record_deletion,
    run_full_update,
    search_journal,
    seed_source_content_hashes,
    session_bootstrap,
    suggest_next_actions,
    update_maps,
    verify_wikis,
    why_file,
)
from .paths import ProjectPathError, ProjectRootError, resolve_root, to_rel  # noqa: F401
from . import agent_loop  # noqa: F401
from .contracts import (  # noqa: F401
    AnalysisTraceEntry,
    ConditionalAnalysis,
    DynamicAnalysis,
    NODE_IDENTITY_VERSION_V0,
    NODE_IDENTITY_VERSION_V1,
    RESERVED_TOP_LEVEL_KEYS,
    RICH_KEYS,
    ResolutionMetadata,
    compute_acs_confidence,
    decode_v1_payload,
    encode_v1_payload,
    get_contracts_info,
    pack_cdia_v1,
    parse_pipeline_line,
    unpack_cdia_v1,
)

_sys.modules["wikifier.health"] = health_module
_sys.modules["wikifier.health_pkg"] = health_module

try:  # optional extra: never required for the core
    from . import mcp  # noqa: F401
except ImportError:
    mcp = None  # type: ignore
