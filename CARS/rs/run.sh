#!/usr/bin/env bash
set -euo pipefail

# Resolve paths relative to this script, not the caller's cwd.
cd "$(dirname "$0")"

# Prefer the project venv (../.venv); fall back to whatever python3 is on PATH.
if [ -x ../.venv/Scripts/python.exe ]; then      # Windows layout
    PY=../.venv/Scripts/python.exe
elif [ -x ../.venv/bin/python ]; then            # POSIX layout
    PY=../.venv/bin/python
else
    PY=python3
fi

"$PY" run_selection.py \
    ../sample_csv/ \
    ../rule_selection/ \
    --atk-nodes 5,6,7,8,9,10 \
    --atk-start-s 300 \
    --ac-thr 65
