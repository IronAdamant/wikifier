"""
Health matrix (🟢/🟡/🔴 per file) — importable as ``wikifier.health``.

Modules:
  store      file_health.json load/save/upsert (+ file_health.md view)
  pending    pending_updates.md work queue
  freshness  content hashes, stale wikis, record-change / mark-green state
  scope      monitored_paths, ghosts, map-first seeding, pruning, validate
  summary    counts + map-first taxonomy, attention lists, barrel reports
  readiness  unattended-daemon readiness + metrics history
  healing    promote Initial stubs once real wikis exist

``_do_*`` functions assume the caller already holds the project lock
(``wikifier.locking.file_lock``); the public names take it themselves.
"""

from .store import (  # noqa: F401
    GREEN,
    HEALTH_JSON,
    HEALTH_MD,
    PENDING_MD,
    RED,
    YELLOW,
    _do_save_health,
    _do_upsert_entry,
    _entry_is_under_root,
    _normalize_to_relative,
    load_health,
    normalize_entry,
    save_health,
    upsert_entries_batch,
    upsert_entry,
)
from .pending import (  # noqa: F401
    _do_add_to_pending,
    _do_remove_from_pending,
    add_to_pending,
    count_pending,
    pending_item_path,
    remove_from_pending,
)
from .freshness import (  # noqa: F401
    _do_mark_green,
    _do_mark_green_checked,
    _do_record_meaningful_edit,
    _find_existing_wiki_file,
    classify_content_dirty,
    compute_source_content_hash,
    get_stale_wikis,
    mark_green,
    mark_wiki_refresh,
    record_meaningful_edit,
    seed_source_content_hashes,
    source_mtime_ns,
)
from .scope import (  # noqa: F401
    PARSEABLE_SOURCE_SUFFIXES,
    detect_scope_risks,
    find_deleted_missing,
    find_ghost_entries,
    prune_deleted_missing,
    prune_health_outside_monitored,
    prune_pending_to_monitored,
    seed_health_for_monitored_sources,
    seed_health_from_map,
    validate_health,
)
from .verify import (  # noqa: F401
    WikiVerificationError,
    public_symbols,
    verify_wiki,
    verify_wikis,
)
from .summary import (  # noqa: F401
    apply_barrel_invalidation_reports,
    get_files_needing_attention,
    get_summary,
)
from .readiness import (  # noqa: F401
    assess_autonomous_readiness,
    read_metrics_history,
    write_metrics_snapshot,
)
from .healing import (  # noqa: F401
    get_healable_stubs,
    get_healing_statistics,
    heal_outdated_stubs,
    heal_with_policy,
)

__all__ = [
    "HEALTH_JSON", "HEALTH_MD", "PENDING_MD", "GREEN", "YELLOW", "RED",
    "load_health", "save_health", "upsert_entry", "upsert_entries_batch", "normalize_entry",
    "add_to_pending", "remove_from_pending", "count_pending", "pending_item_path",
    "mark_green", "record_meaningful_edit", "mark_wiki_refresh",
    "compute_source_content_hash", "classify_content_dirty",
    "seed_source_content_hashes", "source_mtime_ns", "get_stale_wikis",
    "WikiVerificationError", "public_symbols", "verify_wiki", "verify_wikis",
    "seed_health_from_map", "seed_health_for_monitored_sources",
    "find_ghost_entries", "find_deleted_missing", "validate_health", "detect_scope_risks",
    "prune_pending_to_monitored", "prune_health_outside_monitored", "prune_deleted_missing",
    "get_summary", "get_files_needing_attention", "apply_barrel_invalidation_reports",
    "assess_autonomous_readiness", "write_metrics_snapshot", "read_metrics_history",
    "heal_with_policy", "heal_outdated_stubs", "get_healable_stubs", "get_healing_statistics",
    "PARSEABLE_SOURCE_SUFFIXES",
]
