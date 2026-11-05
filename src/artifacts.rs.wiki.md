# src/artifacts.rs

**Role:** Health matrix, pending queue, journal, and folder-card reads.

`file_health.json` is schema version 2. A row can store `public_symbols`, `wiki_hash`, and `source_mtime_ns` from the last mark-green. Those fields are written only when they are set, so an older health file is not rewritten just by being read.

`append_journal` skips an identical action, file, and reason inside 120 seconds. `write_durable` replaces health, journal, and pending files through a synced temp file and a rename; `write_health` and `append_journal` use it. `folder_card` reads `.wikifier_staging/maps/_root.json` or a directory `_index.json`.

Public names: `HealthRow`, `new`, `keep_baseline_from`, `read_health`, `write_health`, `upsert_health_row`, `JournalEntry`, `journal_path`, `read_journal`, `parse_journal`, `JournalWrite`, `append_journal`, `read_pending`, `folder_card`, `write_durable`.
