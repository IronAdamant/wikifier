"""Barrel resolution cache + stale-importer invalidation."""
from ._core import (
    get_barrel_resolutions,
    get_barrel_file_index,
    set_barrel_resolutions,
    set_barrel_file_index,
    invalidate_stale_barrel_entries,
    get_barrel_invalidation_reports,
    get_barrel_cache_summary,
    append_barrel_invalidation_log,
    prune_barrel_resolutions,
)
