#!/usr/bin/env bash
#
# parse_serial.sh -- end-to-end offline rule selection from one Cooja log
# =======================================================================
# Runs the whole CARS/rs/README.md pipeline for a single simulation log:
#
#   sim.log --[parse_serial.py]--> <name>.csv --[run_selection.py]--> outputs
#                                                  pareto_front.csv
#                                                  selected_rules.txt
#                                                  selected_rules.c
#                                                  overlap_report.txt
#
# Usage:
#   ./parse_serial.sh                    # uses ../../sim.log
#   ./parse_serial.sh /path/to/other.log
#
# Everything is auto-derived from the log (attacker IDs, attack start time)
# so the parameters cannot drift away from the data. Override any of them:
#
#   ATK_NODES=22,23,24,25,26 ATK_START_S=300 GENS=400 ./parse_serial.sh
#   SEEDS="1 2 3 4 5" ./parse_serial.sh      # multi-seed reproducibility run
#
set -euo pipefail

# Resolve paths relative to this script, not the caller's cwd.
cd "$(dirname "$0")"

LOG="${1:-../../sim.log}"

# Tunables (defaults from README.md "Usage").
TIME_UNIT="${TIME_UNIT:-us}"      # unit of the Cooja script's `time` variable
AC_THR="${AC_THR:-65}"            # FUZZRID_TAU_Q_PCT
MF_HIGH="${MF_HIGH:-60,90}"       # 50,80 for the pre-Mar-2026 membership funcs
MAX_TERMS="${MAX_TERMS:-4}"
MAX_RULES="${MAX_RULES:-30}"      # Z1 RAM/flash budget
POP="${POP:-120}"
GENS="${GENS:-200}"
TEST_FRAC="${TEST_FRAC:-0.3}"
SEEDS="${SEEDS:-42}"              # space-separated; README suggests 1..10

step() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }

# ---------------------------------------------------------------------------
step "Step 0/4  Locate the log and the Python environment"
# ---------------------------------------------------------------------------
[ -f "$LOG" ] || die "log not found: $LOG"

# The CSV is named after the log, so results are always traceable to their
# source: sim.log -> runs/sim/csv/sim.csv. data.py takes the scenario name
# from the filename prefix before the first '_'.
NAME="$(basename "$LOG")"; NAME="${NAME%.*}"
RUN_DIR="../runs/$NAME"
CSV_DIR="$RUN_DIR/csv"
OUT_DIR="$RUN_DIR/selection"
CSV="$CSV_DIR/$NAME.csv"

# Prefer a project venv (CARS/.venv, then repo-root .venv); else system python3.
PY=""
for cand in ../.venv ../../.venv; do
    if   [ -x "$cand/bin/python" ];        then PY="$cand/bin/python";        break
    elif [ -x "$cand/Scripts/python.exe" ]; then PY="$cand/Scripts/python.exe"; break
    fi
done
[ -n "$PY" ] || PY=python3

"$PY" - <<'EOF' || die "numpy/pandas/pymoo missing -- run ./install_lib.sh first"
import numpy, pandas, pymoo
EOF

echo "log     : $LOG"
echo "python  : $PY"
echo "run dir : $RUN_DIR"

# ---------------------------------------------------------------------------
step "Step 1/4  Derive ground truth from the log"
# ---------------------------------------------------------------------------
# Attacker motes announce themselves at boot; the IDS never runs on them, so
# data.py needs the exact set to label y=1 and to drop attacker observers.
if [ -z "${ATK_NODES:-}" ]; then
    ATK_NODES="$(awk '/Starting 2H-FuzzRID attacker/ {print $2}' "$LOG" \
                 | sort -n -u | paste -sd, -)"
    [ -n "$ATK_NODES" ] || die "no attacker motes found in $LOG -- set ATK_NODES=..."
    echo "attackers   : $ATK_NODES  (auto-detected)"
else
    echo "attackers   : $ATK_NODES  (from ATK_NODES)"
fi

# Attackers behave honestly during warm-up. Label from the moment the LAST
# attacker launches, so no attack row is labelled benign; data.py drops the
# attacker rows before this instant rather than injecting label noise.
if [ -z "${ATK_START_S:-}" ]; then
    ATK_START_S="$(awk '/ATK-LAUNCHED/ {
                          if (match($0, /t=[0-9]+s/)) {
                              v = substr($0, RSTART + 2, RLENGTH - 3) + 0
                              if (v > m) m = v
                          }
                        } END { if (m) print m }' "$LOG")"
    if [ -n "$ATK_START_S" ]; then
        echo "attack start: ${ATK_START_S}s  (last [ATK-LAUNCHED] marker)"
    else
        ATK_START_S=300
        echo "attack start: ${ATK_START_S}s  (no [ATK-LAUNCHED] markers; FUZZRID_T_WARM_S default)"
    fi
else
    echo "attack start: ${ATK_START_S}s  (from ATK_START_S)"
fi

# ---------------------------------------------------------------------------
step "Step 2/4  Parse the serial log into an events CSV"
# ---------------------------------------------------------------------------
mkdir -p "$CSV_DIR"
"$PY" parse_serial.py "$LOG" "$CSV" \
    --time-unit "$TIME_UNIT" \
    --atk-nodes "$ATK_NODES"

# ---------------------------------------------------------------------------
step "Step 3/4  Candidate generation + NSGA-II rule selection"
# ---------------------------------------------------------------------------
# run_selection.py consumes a *directory* of CSVs (one per scenario/run), so
# it reads $CSV_DIR. Drop more parse_serial.py outputs in there to select
# rules across several scenarios at once.

run=0
if [ "$run" -ne 1 ]; then
set -- $SEEDS
N_SEEDS=$#
for seed in $SEEDS; do
    if [ "$N_SEEDS" -gt 1 ]; then
        seed_out="$OUT_DIR/seed_$seed"
        printf '\n-- seed %s --\n' "$seed"
    else
        seed_out="$OUT_DIR"
    fi
    "$PY" run_selection.py "$CSV_DIR" "$seed_out" \
        --atk-nodes "$ATK_NODES" \
        --atk-start-s "$ATK_START_S" \
        --ac-thr "$AC_THR" \
        --mf-high "$MF_HIGH" \
        --max-terms "$MAX_TERMS" \
        --max-rules "$MAX_RULES" \
        --pop "$POP" \
        --gens "$GENS" \
        --test-frac "$TEST_FRAC" \
        --seed "$seed"
done

fi
# ---------------------------------------------------------------------------
step "Step 4/4  Results"
# ---------------------------------------------------------------------------
find "$RUN_DIR" -type f | sort | sed 's/^/  /'
cat <<EOF

Read next:
  $OUT_DIR/selected_rules.txt   knee-point base + overlap with expert R1-R18
  $OUT_DIR/pareto_front.csv     every non-dominated base (train/test F1, FPR)
  $OUT_DIR/selected_rules.c     drop-in block for fuzzrid_fuzzy_infer_ac()
  $OUT_DIR/overlap_report.txt   expert-rule containment across the front
EOF
