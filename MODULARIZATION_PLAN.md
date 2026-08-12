# Wikifier Modularization Plan

## Overview

Several modules in wikifier have grown to 2000+ lines, making them difficult to navigate and maintain. This document outlines a plan for modularizing these "god modules" into coherent package structures.

## Current State (as of v4.6.9)

### Modules Needing Modularization

| Module | Lines | Priority | Complexity |
|--------|-------|----------|------------|
| `wikifier/parsers/javascript.py` | 2681 | High | High - barrel resolution, CDIA integration |
| `wikifier/import_cache.py` | 2588 | High | High - graph algorithms, cycles, ACS |
| `wikifier/health.py` | 2504 | High | Medium - file operations, status tracking |
| `wikifier/mcp/server.py` | 2238 | Medium | Medium - many tool definitions |
| `wikifier/cli.py` | 2034 | Medium | Medium - argparse + API mixing |
| `wikifier/parsers/bree.py` | 2012 | Low | Medium - barrel resolution |
| `wikifier/contracts.py` | 1726 | Low | Low - dataclasses |
| `wikifier/resolution.py` | 1597 | Low | Medium - path resolution |

## Proposed Package Structures

### 1. `wikifier/cache/` (from `import_cache.py`)

**Priority: HIGH** - This is the largest single-concern module with clear boundaries.

```
wikifier/cache/
├── __init__.py          # Public API, backward compatibility exports
├── io.py                # load_cache, save_cache, cache paths
├── files.py             # get/update file data, mtime, content hashing
├── graph.py             # build_dependency_graph, graph_signature
├── cycles.py            # compute_cycles, Tarjan SCC, CIABRE
├── acs.py               # compute_acs_summary, ACS v1.3 logic
├── barrel.py            # barrel resolution, invalidation
├── diagnostics.py       # get_resolution_diagnostics, reporting
└── streaming.py         # generate_update_events, partial results
```

**Functions per module:**
- `io.py`: load_cache, save_cache, load_mtime_index, _get_cache_path, _do_save_cache (~150 lines)
- `files.py`: get/update_file_data, get_mtime, compute_file_content_hash (~200 lines)
- `graph.py`: build_dependency_graph, graph_signature, reverse_dependency ops (~300 lines)
- `cycles.py`: compute_cycles, _tarjan_sccs, get/set_cycles, cycle_analyses, CIABRE (~600 lines)
- `acs.py`: compute_acs_summary, classify_edge_agent_signal, get/set_acs_summary (~400 lines)
- `barrel.py`: get/set_barrel_resolutions, invalidate_stale_barrel_entries, barrel reports (~300 lines)
- `diagnostics.py`: get_resolution_diagnostics, get_unresolved_imports, get_low_confidence_edges (~200 lines)
- `streaming.py`: generate_update_events, run_update_stream (~400 lines)

**Backward Compatibility:**
```python
# wikifier/cache/__init__.py
"""Import cache + graph intelligence (agent-first)."""

from .io import load_cache, save_cache, load_mtime_index
from .files import get_file_data, update_file_data, get_mtime, compute_file_content_hash
from .graph import (
    build_dependency_graph, 
    get_reverse_dependencies,
    set_reverse_dependencies,
    maintain_reverse_dependencies_for_source,
    rebuild_reverse_dependencies
)
from .cycles import compute_cycles, get_cycles, set_cycles, compute_cycle_analyses
from .acs import compute_acs_summary, get_acs_summary, set_acs_summary, classify_edge_agent_signal
from .barrel import (
    get_barrel_resolutions,
    set_barrel_resolutions,
    invalidate_stale_barrel_entries,
    get_barrel_invalidation_reports
)
from .diagnostics import get_resolution_diagnostics, get_unresolved_imports, get_low_confidence_edges
from .streaming import generate_update_events, run_update_stream

# Maintain old import paths
__all__ = [
    'load_cache', 'save_cache', 'load_mtime_index',
    'get_file_data', 'update_file_data',
    # ... (all public functions)
]
```

### 2. `wikifier/health_pkg/` (from `health.py`)

**Priority: HIGH** - Name collision issue (`wikifier.health` shadows module), large module

**Note:** Cannot use `wikifier/health/` as that would conflict with the existing `wikifier/health.py`. Use `health_pkg` temporarily, or do atomic rename.

```
wikifier/health_pkg/
├── __init__.py          # Public API, exports, health() accessor function
├── io.py                # load_health, save_health, paths
├── core.py              # upsert_entry, get_summary
├── pending.py           # pending_updates.md operations
├── status.py            # mark_green, record_meaningful_edit, status mutations  
├── analysis.py          # assess_autonomous_readiness, detect_scope_risks
├── stale.py             # get_stale_wikis, _is_stale_wiki
├── mapfirst.py          # seed_health_from_map, find_ghost_entries, validate_health
├── healing.py           # heal_with_policy, heal_outdated_stubs
└── pruning.py           # prune_pending_to_monitored, prune_health_outside_monitored
```

**Migration Path:**
1. Create `health_pkg/` with all modules
2. Add `wikifier.health_module` alias in `wikifier/__init__.py` pointing to health_pkg
3. Keep `health.py` as thin compatibility shim for one release
4. Update all imports to use `wikifier.health_pkg` or `wikifier.health_module`
5. Remove `health.py` in next major version

### 3. `wikifier/parsers/javascript/` (from `parsers/javascript.py`)

**Priority: HIGH** - Largest single file, complex logic

```
wikifier/parsers/javascript/
├── __init__.py          # parse_javascript_imports (main entry)
├── extract.py           # Import statement extraction patterns
├── resolve.py           # Path resolution (ES modules, CommonJS)
├── barrel.py            # Barrel/re-export handling
├── cdia.py              # CDIA integration for conditionals
└── metadata.py          # Confidence scoring, edge metadata
```

### 4. `wikifier/mcp/tools/` (split `mcp/server.py`)

**Priority: MEDIUM** - Large but lower risk, clear tool boundaries

```
wikifier/mcp/
├── __init__.py
├── server.py            # FastMCP setup, main() entry point (~200 lines)
├── tools/
│   ├── __init__.py
│   ├── core.py          # Core-6: session_bootstrap, check_changes, suggest_next_actions
│   ├── health.py        # health, get_files_needing_attention
│   ├── dependencies.py  # get_dependencies, get_dependents, get_file_wiki
│   ├── maps.py          # update_maps, get_project_status
│   ├── cycles.py        # get_cycles, get_cycle_analyses
│   ├── barrel.py        # get_barrel_reports, barrel operations
│   ├── diagnostics.py   # get_resolution_diagnostics, get_unresolved_imports
│   ├── workflow.py      # record_change, mark_green, prepare_edit
│   └── advanced.py      # heal_stubs, prune operations
├── prompts.py           # MCP prompts (audit_project_health, plan_refactoring, etc)
└── models.py            # Pydantic models (DependencyInfo, FileDependencies, etc)
```

### 5. `wikifier/api.py` + Thin `cli.py`

**Priority: MEDIUM** - Separate concerns: argparse vs library API

**Current issue:** `cli.py` mixes argparse with substantial library functions that should be public API.

**Proposed:**
- `wikifier/api.py`: Public library API functions (run_full_update, check_changes, suggest_next_actions, etc.)
- `wikifier/cli.py`: Thin argparse wrapper calling api.py functions (~300-400 lines max)
- MCP server uses `wikifier.api` directly instead of importing from cli

## Implementation Guidelines

### 1. Backward Compatibility

**Critical:** All existing imports must continue to work. Use `__init__.py` to re-export public API:

```python
# Old code still works:
from wikifier.import_cache import load_cache, compute_cycles

# New code can use:
from wikifier.cache import load_cache
from wikifier.cache.cycles import compute_cycles
```

### 2. Testing Strategy

For each modularization:
1. Create new package structure
2. Move code to new modules
3. Add backward-compatible imports in `__init__.py`
4. Run full test suite: `python -m unittest discover tests`
5. Fix any import errors or test failures
6. Verify wheel builds correctly
7. Test MCP server still works

### 3. Module Size Targets

- Individual modules: 300-600 lines max
- Keep related functions together (cohesion)
- Clear single responsibility per module
- Minimize cross-module dependencies within package

### 4. One Package at a Time

Do not attempt multiple packages in one PR. Each modularization should be:
- Separate PR
- Fully tested
- Documented in CHANGELOG
- Reviewed for backward compatibility

## Recommended Order

1. **`wikifier/cache/`** (from import_cache.py) - Largest, clearest boundaries
2. **`wikifier/health_pkg/`** (from health.py) - Fixes name collision
3. **`wikifier/api.py` split** - Improves library/CLI separation
4. **`wikifier/mcp/tools/`** - MCP tool organization
5. **`wikifier/parsers/javascript/`** - Complex but isolatable

## Benefits

- **Navigability:** New contributors can find code faster
- **Maintainability:** Clear boundaries reduce cognitive load
- **Testing:** Easier to test individual concerns
- **Import time:** Potential for lazy imports to speed startup
- **Name collision:** Fixes `wikifier.health` vs `from wikifier import health` footgun

## Non-Goals

- Do NOT break zero-dependency core
- Do NOT change public API signatures
- Do NOT merge unrelated functions just to hit line counts
- Do NOT create packages for modules <1000 lines (diminishing returns)

## References

- User rule: `Code limit.md` - 600 LOC guideline per file
- CLAUDE.md: "god-module cliff" warning for javascript.py, import_cache.py, etc.
- skills/run.md: "Do not open megamodules for workflow decisions"
