#!/bin/bash
# Thin wrapper around download-plugins.py — all arguments pass through unchanged.
# The Python script is the single source of truth for plugin URLs, hash
# verification, and platform detection. See download-plugins.py for the real
# logic; this file exists so users can run `./scripts/download-plugins.sh` out
# of muscle memory.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON_SCRIPT="${SCRIPT_DIR}/download-plugins.py"

PYTHON=""
for cmd in python3 python; do
  if command -v "$cmd" >/dev/null 2>&1; then
    if "$cmd" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 9) else 1)' 2>/dev/null; then
      PYTHON="$cmd"
      break
    fi
  fi
done

if [ -z "$PYTHON" ]; then
  echo "Error: Python 3.9+ not found. Install from https://python.org or via your package manager." >&2
  exit 1
fi

exec "$PYTHON" "$PYTHON_SCRIPT" "$@"
