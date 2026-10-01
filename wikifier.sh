#!/usr/bin/env bash
# wikifier.sh — thin launcher. Every command is implemented in Python:
#   ./wikifier.sh <command> [args]   ==   python3 -m wikifier <command> [args]
# Set WIKIFIER_PYTHON to choose the interpreter. Run `./wikifier.sh help` for commands.
set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# Source checkout (repo root or wikifier/scripts/): make the package importable without pip.
for candidate in "$here" "$(dirname "$(dirname "$here")")"; do
    if [[ -f "$candidate/wikifier/__init__.py" ]]; then
        export PYTHONPATH="$candidate${PYTHONPATH:+:$PYTHONPATH}"
        break
    fi
done

exec "${WIKIFIER_PYTHON:-python3}" -m wikifier "$@"
