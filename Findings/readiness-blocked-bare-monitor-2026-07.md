# Readiness blocked: bare `.` monitor + no map (Grok-Bevy dogfood)

**Date:** 2026-07-18  
**Context:** Agent session on external project **Grok-Bevy** (Rust workspace) via MCP `session_bootstrap`.  
**Protocol:** `skills/run.md` § *Readiness blocked*.

## Symptom

```text
readiness: "blocked"
scope.ok: false
bare_dot_monitor: true
blockers:
  - monitored_paths is bare '.' — check-changes will thrash...
  - No import map (run update-maps first).
  - No file_health — run seed-health or update-maps.
actions: fix_scope (priority 2), ...
```

Not a MCP auth failure. Session can still call tools; map-first workflow is **unsafe/unready** until unblocked.

## Root cause

1. **No lean `monitored_paths.txt`** → effective monitor is bare `.` → thrash risk on `target/`, caches, large trees.
2. **Never ran `update-maps`** on that project → no import map, no seeded `file_health`.

## Fix applied (Grok-Bevy)

1. Wrote lean `monitored_paths.txt` (`crates/*/src/`, templates `src/`, key docs).
2. Wrote lean `map_paths.txt` (crate `src/` roots only).
3. `update_maps(full=true)` → re-bootstrap → `ready_for_daemon`, Map Ready, `scope.ok: true`.

## Agent rule

On `readiness: blocked`, **do not** invent architecture work first — run **`fix_scope` + `update-maps`** from `actions[]` / `blockers[]`, then continue.

## Follow-up for Wikifier package update

- **Done in 4.6.8:** `wikifier init` seeds comment-guided lean `monitored_paths.txt` + `map_paths.txt` templates (not a silent bare `.` only).
- Keep `skills/run.md` § Readiness blocked as the agent contract for this case.
