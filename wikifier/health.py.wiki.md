# wikifier/health.py

Scalable implementation of the Documentation Health Matrix (introduced in M2-Rem-02).

## Purpose
Provides fast, JSON-backed storage and querying for file health status. Designed to scale from small projects to massive monorepos while maintaining backward compatibility with the human-readable `file_health.md`.

## Key Design Decisions (Long-term Scalability)
- `file_health.json` is the primary source of truth (O(1) lookups and updates).
- `file_health.md` is generated from JSON (keeps human experience simple).
- Automatic migration from existing Markdown on first use.
- Clean separation between data layer (Python) and CLI (shell + Python).
- Ready for future extensions: directory-level health, summary views, sharding for very large repos.

## Main Functions
- `load_health(root)` — Loads (and migrates if needed)
- `save_health(root, data)` — Saves + regenerates Markdown
- `upsert_entry(root, file, status, reason)` — Add/update a file
- `get_summary(root)` — Fast aggregate counts
- `get_files_needing_attention(root)` — Efficient filtering

## Usage
```bash
python -m wikifier.health summary
python -m wikifier.health needs-attention
```

This module is the foundation for making Wikifier's health system viable on large and massive codebases.
