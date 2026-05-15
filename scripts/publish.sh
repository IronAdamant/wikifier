#!/bin/bash
# Quick publish helper for Wikifier to PyPI
# Usage:
#   ./scripts/publish.sh test     # Upload to TestPyPI
#   ./scripts/publish.sh prod     # Upload to real PyPI

set -euo pipefail

if [ $# -eq 0 ]; then
    echo "Usage: $0 [test|prod]"
    exit 1
fi

MODE="$1"

# Clean previous builds
rm -rf build/ dist/ *.egg-info/ 2>/dev/null || true

echo "Building wikifier package..."
python -m build --sdist --wheel .

echo "Checking distribution..."
twine check dist/*

if [ "$MODE" = "test" ]; then
    echo "Uploading to TestPyPI..."
    twine upload --repository testpypi dist/*
    echo ""
    echo "Test install with:"
    echo "  pip install --index-url https://test.pypi.org/simple/ --extra-index-url https://pypi.org/simple wikifier"
elif [ "$MODE" = "prod" ]; then
    echo "Uploading to PyPI..."
    twine upload dist/*
    echo ""
    echo "Install with: pip install wikifier"
else
    echo "Unknown mode: $MODE (use 'test' or 'prod')"
    exit 1
fi
