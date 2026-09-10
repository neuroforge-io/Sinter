#!/bin/sh
# Run from this folder even when the launcher is opened from a file manager.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ -x .venv/bin/python ]; then
    exec .venv/bin/python start.py "$@"
elif command -v python3 >/dev/null 2>&1; then
    exec python3 start.py "$@"
elif command -v python >/dev/null 2>&1; then
    exec python start.py "$@"
else
    printf '%s\n' 'Sinter needs Python 3.10 or newer. Install it from python.org and open this launcher again.'
    printf '%s' 'Press Enter to close: '
    read -r answer
    exit 1
fi
