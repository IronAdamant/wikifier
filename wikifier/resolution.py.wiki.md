# wikifier/resolution.py

**Purpose:** central JS/TS specifier resolution and path canonicalization: strategies for relative paths, tsconfig `paths`, package `imports`, workspaces, package `exports` (conditions + wildcards) and bare internal modules, with rich `ResolutionMetadata`. Unresolved relative specifiers return `resolved_file=None` (attempted path only in metadata). `to_canonical_rel` / `canonical_for_bree` give stable symlink-safe identities.
