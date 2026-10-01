# wikifier/parsers/bree/_bree.py

**Purpose:** barrel & re-export expansion engine (BREE): detectors, re-export extractors, bounded chain expansion (depth 3, cycle-safe) and the persistent `BarrelResolutionCache` (`_barrel_resolutions`, `_barrel_file_index` reverse index, mtime snapshots).

Persistence goes straight to `cache_store` meta keys (`_persist_barrel_cache`); one session cache per process/root, flushed per file or once per batched run. Invalidation lookups are exact canonical keys (`_brc_canonical`). Package `exports` resolution delegates to `wikifier.resolution`.
