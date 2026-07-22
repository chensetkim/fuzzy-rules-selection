#!/usr/bin/env bash
set -euo pipefail

# Resolve paths relative to this script, not the caller's cwd.
cd "$(dirname "$0")"

# Prefer the project venv (../.venv); create it if it does not exist.
if [ -x ../.venv/Scripts/python.exe ]; then      # Windows layout
	PY=../.venv/Scripts/python.exe
elif [ -x ../.venv/bin/python ]; then            # POSIX layout
	PY=../.venv/bin/python
else
	python3 -m venv ../.venv
	PY=../.venv/bin/python
fi

"$PY" -m pip install --upgrade pip setuptools wheel
"$PY" -m pip install numpy pandas pymoo
