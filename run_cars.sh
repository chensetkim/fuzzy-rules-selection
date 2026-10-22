#!/usr/bin/env bash
#
# run_cars.sh -- CARS rule selection from start to end, in one command
# ===================================================================
#   0 check     venv, python libs, data/processed CSVs
#   1 parse     Cooja logs -> CSVs           (OFF unless --parse)
#   2 select    primary + round-holdout      methods/cars/run_real_selection.py
#   3 loso      leave-one-scenario-out S1-6  methods/cars/run_loso.py
#   4 finalize  best-F1 re-pick (2 splits)   methods/cars/finalize_selection.py
#   5 summary   SUMMARY.md                   scripts/summarize_cars.py
#
# Usage:
#   ./run_cars.sh                          full run, settings below
#   QUICK=1 ./run_cars.sh                  ~1-2 min smoke test (tiny pop/gens/sample)
#   SEEDS="1 2 3 4 5" ./run_cars.sh        multi-seed; SUMMARY.md shows mean ± std
#   MAX_RULES=30 SEED=7 ./run_cars.sh      any setting can be overridden
#   ./run_cars.sh --parse                  also re-parse data/raw/logs -> data/processed
#   ./run_cars.sh --out outputs/cars/run_X --from loso
#                                          resume an earlier run from a step
#                                          (its config.txt is reused)
#
# Each run writes to its own folder and never overwrites earlier results:
#   outputs/cars/run_<date>_<time>/
#     config.txt   SUMMARY.md
#     seed_<s>/primary/ round_holdout/ loso/S1..S6/ logs/
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# ---------------------------------------------------------------------------
# Settings (override with VAR=value ./run_cars.sh)
# ---------------------------------------------------------------------------
QUICK="${QUICK:-0}"
if [ "$QUICK" = 1 ]; then q() { echo "$1"; }; else q() { echo "$2"; }; fi

SEEDS="${SEEDS:-${SEED:-42}}"               # space-separated list
MIN_RULES="${MIN_RULES:-12}"                # 12
MAX_RULES="${MAX_RULES:-35}"                # 35
MF_HIGH="${MF_HIGH:-50,80}"                 # High MF: 0 at 50 -> 100 at 80
AC_THR="${AC_THR:-65}"                      # FUZZRID_TAU_Q_PCT
TEST_FRAC="${TEST_FRAC:-0.3}"                # 30% test data
MAX_TERMS="${MAX_TERMS:-4}"                 # max number of terms in a rule
MIN_SUPPORT="${MIN_SUPPORT:-0.005}"          # min support for a rule
CONF_MARGIN="${CONF_MARGIN:-0.15}"           # confidence margin for rule selection
POP="${POP:-$(q 20 150)}"                   # select + finalize
GENS="${GENS:-$(q 5 250)}"                  # number of generations
TRAIN_SAMPLE="${TRAIN_SAMPLE:-$(q 3000 40000)}" # number of training samples
LOSO_POP="${LOSO_POP:-$(q 20 80)}"          # loso
LOSO_GENS="${LOSO_GENS:-$(q 5 120)}"        # number of generations for loso
LOSO_TRAIN="${LOSO_TRAIN:-$(q 3000 30000)}" # number of training samples for loso
CSV_ROOT="${CSV_ROOT:-data/processed}"      # path to processed CSV data
# Attack start for labelling is fixed at 300 s in common/real_data.py.

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
STEPS=(check parse select loso finalize summary)
DO_PARSE=0; FROM=check; OUT=""
usage() { sed -n '2,25p' "$0" | sed 's/^# \{0,1\}//'; exit "${1:-0}"; }
while [ $# -gt 0 ]; do
    case "$1" in
        --parse) DO_PARSE=1 ;;
        --from)  FROM="${2:?--from needs a step}"; shift ;;
        --out)   OUT="${2:?--out needs a folder}"; shift ;;
        -h|--help) usage ;;
        *) echo "unknown argument: $1" >&2; usage 1 ;;
    esac
    shift
done
[[ " ${STEPS[*]} " == *" $FROM "* ]] || { echo "--from must be one of: ${STEPS[*]}" >&2; exit 1; }

bold() { printf '\n\033[1m== %s ==\033[0m\n' "$*"; }
die()  { printf '\033[31merror:\033[0m %s\n' "$*" >&2; exit 1; }
idx()  { local i; for i in "${!STEPS[@]}"; do [ "${STEPS[$i]}" = "$1" ] && echo "$i"; done; }
want() { [ "$(idx "$1")" -ge "$(idx "$FROM")" ]; }

# Run one step, logging everything to $log and echoing only the result lines.
run_step() {
    local name="$1" log="$2"; shift 2
    local t0=$SECONDS
    printf '  %-28s ' "$name"
    if "$@" > "$log" 2>&1; then
        printf 'ok (%ds)\n' $((SECONDS - t0))
        grep -hE "knee base|expert R1-R18 on this test|^\[finalize\]" "$log" \
            | sed -E 's|^\[finalize\] [^ ]+ |[finalize] |; s| -> .*||; s/^/      /' || true
    else
        printf '\033[31mFAILED\033[0m (%ds) -- last lines of %s:\n' $((SECONDS - t0)) "$log"
        tail -n 15 "$log" | sed 's/^/      /'
        exit 1
    fi
}

# ---------------------------------------------------------------------------
# Run folder + config
# ---------------------------------------------------------------------------
if [ -n "$OUT" ] && [ "$FROM" != check ]; then
    [ -f "$OUT/config.txt" ] || die "$OUT/config.txt not found -- --from needs an earlier run folder"
    # Resume: reuse the original settings so finalize matches select.
    # shellcheck disable=SC1091
    source "$OUT/config.txt"
    echo "resuming $OUT from '$FROM' with its config.txt"
else
    OUT="${OUT:-outputs/cars/run_$(date +%Y-%m-%d_%H%M)$( [ "$QUICK" = 1 ] && echo _quick)}"
    [ -e "$OUT" ] && die "$OUT already exists -- pick another --out"
    mkdir -p "$OUT"
    COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo none)$(git diff --quiet 2>/dev/null || echo -dirty)"
    cat > "$OUT/config.txt" <<EOF
# run_cars.sh settings ($(date '+%Y-%m-%d %H:%M'), commit $COMMIT)
QUICK=$QUICK
SEEDS="$SEEDS"
MIN_RULES=$MIN_RULES
MAX_RULES=$MAX_RULES
MF_HIGH=$MF_HIGH
AC_THR=$AC_THR
TEST_FRAC=$TEST_FRAC
MAX_TERMS=$MAX_TERMS
MIN_SUPPORT=$MIN_SUPPORT
CONF_MARGIN=$CONF_MARGIN
POP=$POP
GENS=$GENS
TRAIN_SAMPLE=$TRAIN_SAMPLE
LOSO_POP=$LOSO_POP
LOSO_GENS=$LOSO_GENS
LOSO_TRAIN=$LOSO_TRAIN
CSV_ROOT=$CSV_ROOT
# fixed: ATK_START_S=300 (common/real_data.py), expert rules not injected
EOF
fi
echo "run folder: $OUT"
echo "seeds: $SEEDS | rules $MIN_RULES-$MAX_RULES | MF_HIGH=$MF_HIGH | AC_THR=$AC_THR | pop/gens $POP/$GENS (loso $LOSO_POP/$LOSO_GENS)"

COMMON=(--csv-root "$CSV_ROOT" --ac-thr "$AC_THR" --max-terms "$MAX_TERMS"
        --min-support "$MIN_SUPPORT" --conf-margin "$CONF_MARGIN"
        --mf-high "$MF_HIGH" --min-rules "$MIN_RULES" --max-rules "$MAX_RULES")

# ---------------------------------------------------------------------------
# 0. check
# ---------------------------------------------------------------------------
if want check; then
    bold "0/5 check"
    if [ -x .venv/bin/python ]; then PY=.venv/bin/python
    elif [ -x .venv/Scripts/python.exe ]; then PY=.venv/Scripts/python.exe
    else PY=python3; fi
    if ! "$PY" -c "import numpy, pandas, pymoo" 2>/dev/null; then
        echo "  numpy/pandas/pymoo missing -> scripts/install_lib.sh"
        ./scripts/install_lib.sh
        PY=.venv/bin/python
    fi
    echo "  python : $PY"
else
    PY=.venv/bin/python; [ -x "$PY" ] || PY=python3
fi
export PYTHONUNBUFFERED=1

# ---------------------------------------------------------------------------
# 1. parse (optional)
# ---------------------------------------------------------------------------
if want parse && [ "$DO_PARSE" = 1 ]; then
    bold "1/5 parse  data/raw/logs -> $CSV_ROOT"
    mkdir -p "$OUT/logs"
    for env in mobile static; do for r in r1 r2 r3; do for n in 3 6 9; do
        [ -d "data/raw/logs/$env/$r/$n" ] || continue
        run_step "$env/$r/$n" "$OUT/logs/parse_${env}_${r}_${n}.log" \
            env LOG_PATH="$ROOT/data/raw/logs/$env/$r/$n" OUTPUT_PATH="$ROOT/$CSV_ROOT/$env/$r/$n" \
            ./scripts/parse_serial.sh
    done; done; done
elif want parse; then
    bold "1/5 parse  (skipped -- use --parse to rebuild CSVs from logs)"
fi

if want check; then
    n_csv=$(find "$CSV_ROOT" -name '*.csv' | wc -l)
    echo "  CSVs   : $n_csv in $CSV_ROOT"
    [ "$n_csv" -gt 0 ] || die "no CSVs in $CSV_ROOT -- run with --parse"
    [ "$n_csv" -eq 108 ] || echo "  warning: expected 108 CSVs (2 env x 3 rounds x 3 atk counts x 6 scenarios)"
fi

# ---------------------------------------------------------------------------
# 2-4. per seed: select, loso, finalize
# ---------------------------------------------------------------------------
for seed in $SEEDS; do
    S="$OUT/seed_$seed"; mkdir -p "$S/logs"

    if want select; then
        bold "2/5 select  seed $seed  (primary + round-holdout)"
        run_step "run_real_selection" "$S/logs/select.log" \
            "$PY" methods/cars/run_real_selection.py "${COMMON[@]}" --out-root "$S" \
            --pop "$POP" --gens "$GENS" --train-sample "$TRAIN_SAMPLE" \
            --test-frac "$TEST_FRAC" --seed "$seed"
    fi

    if want loso; then
        bold "3/5 loso  seed $seed  (S1..S6)"
        run_step "run_loso" "$S/logs/loso.log" \
            "$PY" methods/cars/run_loso.py "${COMMON[@]}" --out-root "$S/loso" \
            --pop "$LOSO_POP" --gens "$LOSO_GENS" --train-sample "$LOSO_TRAIN" --seed "$seed"
    fi

    if want finalize; then
        bold "4/5 finalize  seed $seed  (best-F1 within $MIN_RULES-$MAX_RULES rules)"
        for split in primary round_holdout; do
            [ -f "$S/$split/pareto_front.csv" ] || die "$S/$split/pareto_front.csv missing -- run from 'select'"
            # Same seed / train-sample / test-frac as select, or the pool won't match.
            run_step "finalize $split" "$S/logs/finalize_$split.log" \
                "$PY" methods/cars/finalize_selection.py "${COMMON[@]}" --split "$split" \
                --out-dir "$S/$split" --train-sample "$TRAIN_SAMPLE" \
                --test-frac "$TEST_FRAC" --seed "$seed"
        done
    fi
done

# ---------------------------------------------------------------------------
# 5. summary
# ---------------------------------------------------------------------------
bold "5/5 summary"
"$PY" scripts/summarize_cars.py "$OUT"
