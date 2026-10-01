# wikifier/mcp/server_impl.py

**Purpose:** the FastMCP server — a thin adapter over `wikifier.api` (no subprocess, no fallback path). Each tool resolves `project_root` strictly, calls the library, and formats text when asked. Mutators run under `call_with_deadline` and mark `may_still_complete` on timeout. Also: resources (`library`, `health`, `pending`, `journal/{date}`) and workflow prompts. Tool catalogue: `wikifier/mcp/README.md`.

- Workflow tools: `check_changes`, `record_change`, `record_changes` (batch from git: reasons by path/glob/dir, `only`, `green`, `dry_run`), `record_deletion`, `mark_green` (`force`; returns verification `issues` on refusal), `verify_wikis`, `session_bootstrap`, `prepare_edit`, `suggest_next_actions`, `list_core_tools`.
- Lookup: `get_dependencies` (`detail="compact"` default — text lists internal targets + external names; `full` / `low_confidence_only` / `unresolved_only` give per-edge records), `get_dependents`, `get_cycles`, `get_barrel_reports`, `get_resolution_diagnostics`, `get_file_wiki`, `why_file`, `search_journal`, `list_paths`.
- Status/maintenance: `get_project_status`, `get_files_needing_attention`, `get_incremental_status`, `get_current_project_root`, `health`, `validate`, `journal`, `issues`, `update_maps` (`UpdateMapsResult`), `seed_source_content_hashes`, `list_healable_stubs`, `heal_stubs`.
- Resource handlers: `get_library`, `get_health_matrix`, `get_pending_updates`, `get_journal` (`wikifier://library|health|pending|journal/{date}`). `main` is the `wikifier-mcp` entry point.
- Prompts: `audit_project_health`, `find_architectural_smells`, `generate_project_health_report`, `plan_refactoring`, `review_pending_changes`, `understand_codebase_structure`, `review_recent_changes`, `onboard_to_module`.
