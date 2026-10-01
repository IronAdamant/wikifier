# wikifier/health_pkg (= `wikifier.health`)

**Purpose:** the 🟢/🟡/🔴 health matrix, split by concern:

| Module | Contents |
|---|---|
| `store` | `GREEN`/`YELLOW`/`RED`, `HEALTH_JSON`/`HEALTH_MD`/`PENDING_MD`; `load_health`/`save_health` (atomic) + `.md` view, `upsert_entry`/`upsert_entries_batch`, key canonicalization/pruning, `normalize_entry` (keeps `public_symbols`, `verification`, `source_mtime_ns`) |
| `pending` | `pending_updates.md` queue: `add_to_pending`, `remove_from_pending`, `count_pending`, `pending_item_path` (exact path) |
| `freshness` | `compute_source_content_hash`, `source_mtime_ns`, `classify_content_dirty`, `seed_source_content_hashes`, `get_stale_wikis`, `record_meaningful_edit`, `mark_wiki_refresh`, `mark_green` → `_do_mark_green_checked` (verifies, then one save; refuses missing paths) |
| `wikis` | where a file's wiki lives (`_find_existing_wiki_file`: `<file>.wiki.md`, `<stem>.md`, `WIKI_DIRS`) and `sha256:` fingerprints; shared by `freshness` and `verify` so neither imports the other |
| `verify` | `public_symbols`, `verify_wiki` (diff vs last Green baseline), `verify_wikis` (audit), `WikiVerificationError` |
| `scope` | `PARSEABLE_SOURCE_SUFFIXES`, monitored_paths, `find_ghost_entries`, `find_deleted_missing`, map-first seeding (`seed_health_from_map`, `seed_health_for_monitored_sources`), `prune_pending_to_monitored` (keeps mapped + `keep`), `prune_health_outside_monitored` (keeps mapped), `prune_deleted_missing`, `validate_health`, `detect_scope_risks` |
| `summary` | `get_summary` (counts, stub/actionable taxonomy, `green_breakdown`), `get_files_needing_attention`, `apply_barrel_invalidation_reports` |
| `readiness` | `assess_autonomous_readiness` tiers, `write_metrics_snapshot` / `read_metrics_history` |
| `healing` | `heal_with_policy`, `heal_outdated_stubs`, `get_healable_stubs`, `get_healing_statistics` |

`_do_*` functions expect the caller to hold `locking.file_lock`.
