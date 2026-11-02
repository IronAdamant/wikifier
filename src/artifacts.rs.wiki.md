# src/artifacts.rs

**Role:** Health matrix, pending queue, journal, and folder-card reads.

`file_health.json` is schema version 2. A row can store `public_symbols`, `wiki_hash`, and `source_mtime_ns` from the last mark-green. Those fields are written only when they are set, so an older health file is not rewritten just by being read.

`append_journal` skips an identical action, file, and reason inside 120 seconds. `folder_card` reads `.wikifier_staging/maps/_root.json` or a directory `_index.json`.
