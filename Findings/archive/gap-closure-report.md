# Gap Closure Report — Agent-Focused Project Wiki

**Program:** Gap Closure Swarms  
**Baseline:** v4.5.2 → worktree post-gap-closure  
**Completed:** 2026-07-09  
**subid:** gap-swarm-coord  

## North star

Wikifier = any project's **agent-focused wiki**: first setup builds a **map**; later agents only touch files that need update/remove/change; MCP for anytime lookup; humans observe via thin HTML. Map is automated; wiki **prose** is agent-filled.

## Gap matrix

| ID | Gap | Severity | Status | Evidence |
|----|-----|----------|--------|----------|
| G1 | Product loop under-documented | S1 | **Closed** | README first-run + steady-state; protocol session block; init stdout |
| G2 | First setup map vs semantic investigate | S1 | **Closed** | Honest “map first, wiki later” in README/protocol/init |
| G3 | Agents re-touch green / full-tree | S1 | **Closed** | `suggest_next_actions` selective; protocol SELECTIVE WORK |
| G4 | ACS noise (external/bare as oracle) | S1 | **Closed** | `actionable_low_conf_edges` + demote external; suggest uses it; tests |
| G5 | `health` name shadow | S1 | **Closed** | `health_module` export; MCP importlib; tests; docs |
| G6 | Dual shell/Python residue | S2 | **Closed** (partial) | Pure-Py: check/record/mark/deletion/suggest/validate; launchers synced; shell init improved |
| G7 | Deletion / ghost health entries | S1 | **Closed** | `find_ghost_entries`; check_changes marks ghosts; record_deletion + BRC prune; tests |
| G8 | Issue tracker overclaim | S2 | **Closed** | Docs: journal/pending = audit queue not Jira |
| G9 | Language coverage honesty | S1 | **Closed** | Deep maps = py/js/ts only (README/protocol/init) |
| G10 | Sample dogfood cache vs health | S2 | **Closed** (smoke) | llama_index + redox check/suggest; contract: monitored ≠ map scope documented |
| G11 | Monitor/daemon ops | S2 | **Closed** | Daemon maps interval default 600s; `WIKIFIER_DAEMON_MAPS=0`; start/stop smoke |
| G12 | Complexity / agent-hostile surface | S2→**Closed** | **Closed** | Harnesses → tests/selftest/; AGENT MAP docs; MCP Core 6; dual-path legend; bree/health headers thinned |

## Fix backlog (executed)

1. W1-A G5 health_module + tests  
2. W1-B G4 ACS actionable fields + filter  
3. W1-C/G3 suggest selective + MCP delegates to lib  
4. W1-E G7 ghosts + record_deletion prune + CLI routes  
5. W1-D docs/protocol/README  
6. W2 init agent first-run lines; daemon maps throttle; dogfood smoke  

## Wave notes

### Wave 0 — Investigation
Three explore agents (INV-CONTRACT, INV-TRUST, INV-OPS) produced severity-ranked proposals. Coordinator implemented high-leverage fixes without language expansion or dashboard growth.

### Wave 1–2 — Implementation
- `wikifier/import_cache.py` — `_edge_is_external_noise`, ACS v1.1 actionable fields  
- `wikifier/cli.py` — selective suggest, record_deletion prune, check ghosts, CLI routes  
- `wikifier/health.py` — `find_ghost_entries`, validate ghosts  
- `wikifier/mcp/server.py` — suggest → library  
- `wikifier/__init__.py` — `health_module`  
- `wikifier/daemon.py` — maps interval  
- `wikifier/scripts/wikifier.sh` + root — init messaging  
- `tests/test_gap_closure.py` — 4 new tests  
- README + skills/run.md — contracts  

### Wave 3 — Verification
- **34/34** unittest OK  
- Dogfood: llama_index / redox check-changes + suggest (selective copy)  
- Daemon start/status/stop on temp fixture with `WIKIFIER_DAEMON_MAPS=0`  

## Residual / deferred

| Item | Reason |
|------|--------|
| G12 full megamodule split (js/bree) | Not required for navigability after AGENT MAP + harness extract |
| update-maps honor monitored_paths | Compat risk; document scope instead |
| Unshadow package attr `health` to module only | Breaking for `from wikifier import health` function API |
| Multi-month daemon proof | Out of scope; smoke + runbook only |
| New language parsers | Explicit non-goal |

## Agent contract (canonical)

**First-run:** `init` → `update-maps` → `health --summary` → `suggest-next`  
**Steady-state:** `check-changes` → edit 🔴/🟡 only → `record-change` → wiki → `mark-green` → `update-maps` if structure changed; `record-deletion` on remove  
**Lookup anytime:** MCP status / wiki / deps  
**Limits:** deep maps py/js/ts; journal≠Jira; not fully autonomous without agent judgment  

## Tests

```bash
python3 -m unittest discover tests   # 34 tests
```
