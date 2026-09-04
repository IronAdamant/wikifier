# wikifier/import_cache.py

**Role:** Backward-compat shim. Real implementation lives in `wikifier.cache` (`from .cache import *`).

**Agent note:** Do not open `wikifier/cache/_core.py` for workflow. Prefer library/CLI Core 6. Use this module only when callers still import `wikifier.import_cache`.

**Exports:** Re-exports cache load/save, reverse deps, cycles, ACS, barrels, diagnostics (see module `__all__`). Some private noise helpers exist via star-import even if omitted from `__all__`.
