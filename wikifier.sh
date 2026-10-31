#!/usr/bin/env bash
# Launch the Rust wikifier binary. Prefers WIKIFIER_BIN, then a local build, then cargo run.
set -euo pipefail
here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
if [[ -n "${WIKIFIER_BIN:-}" ]]; then
  exec "$WIKIFIER_BIN" "$@"
fi
if [[ -x "$here/target/release/wikifier" ]]; then
  exec "$here/target/release/wikifier" "$@"
fi
if [[ -x "$here/target/debug/wikifier" ]]; then
  exec "$here/target/debug/wikifier" "$@"
fi
exec cargo run --quiet --manifest-path "$here/Cargo.toml" -- "$@"
