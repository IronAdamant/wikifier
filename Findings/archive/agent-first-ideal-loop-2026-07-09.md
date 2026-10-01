# Agent-first ideal-loop tracking (2026-07-09)

**Package target:** 4.6.x  
**subid:** agent-ideal-loop  

North star: lookup map → touch only what needs work → record *why* → refresh prose → mark trusted → remap only if structure moved.

## Checklist (ideal-loop items)

| ID | Item | Status | Notes |
|----|------|--------|-------|
| A1 | Content-honest dirty (not mtime-only Yellow) | ✅ | `source_content_hash` + check_changes skip |
| A2 | `session_bootstrap` single snapshot | ✅ | library + CLI + MCP |
| A3 | Structured dispatchable `suggest_next_actions` | ✅ | `actions[]` with kind/file/priority |
| A4 | `prepare_edit` / lookup preflight | ✅ | wiki/status/deps/dependents |
| A5 | Journal search + why-for-file | ✅ | `search_journal` / `why_file` |
| A6 | Core daily surface documented | ✅ | protocol + MCP README |
| A7 | ACS actionable default on suggest | ✅ | actions + acs_note |
| D1 | Wiki section-patch API | deferred | full rewrite still default; not blocking |
| D2 | `wikifier attach` external profiles | deferred | dual-scope + readiness cover main risk |
| D3 | Shell-as-launcher-only finish | partial | mutators already pure-Py |

## Change log (this wave)

- `wikifier/agent_loop.py` — bootstrap, preflight, journal search, action builder
- `wikifier/health.py` — source content hash helpers; mark-green captures source hash
- `wikifier/cli.py` — content-honest check_changes; structured suggest; CLI routes
- `wikifier/mcp/server.py` — Core tools wire to library
- `tests/test_agent_loop.py` — deep stretch unit tests
- Protocol / MCP README Core surface notes
- Version 4.6.0; patch **4.6.1** — no-baseline Green rewrite must Yellow (no post-edit hash seed)

## Design tests applied

1. Saves tokens on next turn?  
2. Reduces selective-loop steps?  
3. Dispatchable returns?  
4. Matrix more trustworthy?  
5. Human-only feature deprioritized?

## Deferred (explicit, not silent)

- Wiki section patch API  
- Attach/profile command pack  
- Full multi-lang resolution depth  
