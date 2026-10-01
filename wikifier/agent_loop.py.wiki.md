# wikifier/agent_loop.py

**Purpose:** session helpers behind the Core tools: `session_bootstrap` (health taxonomy, readiness, ACS headline, root folder card, `actions[]`), `prepare_edit` (status, wiki, dependencies with `resolved_path`, dependents from the SQLite edge index, cycle flag, recent journal), `search_journal`, `why_file`, `build_structured_actions`, `list_core_tools` (6 core tools; `record_changes` / `verify_wikis` listed as advanced), `resolve_dependents_from_cache` (dependents from an in-memory cache dict, any historical reverse-index shape). All take a strict `project_root`.
