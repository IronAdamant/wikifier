"""
Wikifier health package - modularized health matrix and status tracking.

This package provides health matrix management, file status tracking,
wiki freshness detection, and autonomous readiness assessment.

Public API (backward compatible with wikifier.health):
- I/O: load_health, save_health
- Status: upsert_entry, mark_green, record_meaningful_edit, mark_wiki_refresh
- Analysis: get_summary, assess_autonomous_readiness, detect_scope_risks
- Stale detection: get_stale_wikis, compute_source_content_hash, classify_content_dirty
- Map-first: seed_health_from_map, find_ghost_entries, validate_health
- Pending: add_to_pending, remove_from_pending, count_pending
- Healing: heal_with_policy, heal_outdated_stubs, get_healable_stubs
- Pruning: prune_pending_to_monitored, prune_health_outside_monitored
- Utilities: get_files_needing_attention, apply_barrel_invalidation_reports

All functions maintain backward compatibility with the original wikifier.health module.
"""

# Re-export everything from the monolithic implementation
from ..health_impl import *
# Explicitly import private functions needed by tests
from ..health_impl import _entry_is_under_root

__all__ = [
    # Constants
    'HEALTH_JSON', 'HEALTH_MD', 'PENDING_MD',
    # I/O operations
    'load_health', 'save_health',
    # Status operations
    'upsert_entry', 'upsert_entries_batch', 'mark_green', 'record_meaningful_edit', 'mark_wiki_refresh',
    # Analysis
    'get_summary', 'assess_autonomous_readiness', 'detect_scope_risks',
    'get_files_needing_attention', 'write_metrics_snapshot', 'read_metrics_history',
    # Content hashing and staleness
    'compute_source_content_hash', 'classify_content_dirty', 
    'seed_source_content_hashes', 'get_stale_wikis',
    # Map-first operations  
    'seed_health_from_map', 'seed_health_for_monitored_sources',
    'find_ghost_entries', 'validate_health',
    # Pending operations
    'add_to_pending', 'remove_from_pending', 'count_pending',
    # Pruning
    'prune_pending_to_monitored', 'prune_health_outside_monitored',
    # Healing
    'heal_with_policy', 'heal_outdated_stubs', 'get_healable_stubs',
    'get_healing_statistics',
    # Barrel integration
    'apply_barrel_invalidation_reports',
    # Private functions needed by tests
    '_entry_is_under_root',
]
