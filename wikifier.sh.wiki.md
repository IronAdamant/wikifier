# wikifier.sh

**Role:** POSIX launcher for the std-only Rust binary.

It execs `WIKIFIER_BIN` when that is set, then `target/release/wikifier`, then `target/debug/wikifier`, and otherwise `cargo run` against this repo's `Cargo.toml`. It does not implement commands itself.
