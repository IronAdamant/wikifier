# CONTRIBUTING.md

**Role:** How to change Wikifier without adding dependencies.

New commands go in `src/api.rs` and `src/main.rs`, with a test and a `skills/run.md` update. The launchers only exec the binary. After an edit, record the change, refresh that file's wiki, and mark it green. CI pins Rust 1.83.0 and runs the tests on Ubuntu, macOS, and Windows.
