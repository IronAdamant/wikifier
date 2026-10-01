# wikifier/serve.py

**Purpose:** localhost server for the human dashboard (`wikifier serve [port]`, default 8787; `main`). `DashboardHandler` serves project files read-only, plus a few `/__wikifier/*` endpoints.

- `GET /__wikifier/status` — `wikifier_serve`, version, project, allowed commands, `api` list.
- `GET /__wikifier/api/<name>` — read-only JSON over the library: `bootstrap` (session_bootstrap), `file?path=` (prepare_edit + wiki text + health entry), `dependencies?path=[&detail=full]` (compact by default), `dependents?path=`, `cycles`, `journal?query=`, `diagnostics` (cache status, ACS, resolution diagnostics, barrels, cycle summary, map coverage, metrics history). Paths go through `paths.to_rel`: outside the root → 400; unknown endpoint → 404.
- `POST /__wikifier/run` — runs one allow-listed command (`check-changes`, `update-maps`, `update-maps --full`) in-process; `POST /__wikifier/shutdown` stops the server.
- Root comes from `paths.resolve_root` (strict: a missing root is an error).
- Binds 127.0.0.1 only. Pages: `index.html` (deployed), `index.v2.html` / `diagnostics.v2.html` (proposed redesign, repo only).
