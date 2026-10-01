# wikifier/streaming.py

**Purpose:** `update-maps --stream`. Runs `api.run_full_update` on a worker thread and yields `ProgressEvent_v1` dicts: `start`, `scope_applied`, one `file_parsed` per file, `partial_ready` when the budget left work, `complete`. The map is persisted normally; re-running resumes (already-parsed files are clean).
