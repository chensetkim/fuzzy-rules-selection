# run_common.sh -- shared plumbing for run_cars.sh and run_thfis.sh
# ==================================================================
# Sourced (not executed) after the runner has set:
#   ROOT       repo root (the runner cd's there first)
#   METHOD     cars | thfis   (output folder outputs/<METHOD>/run_<stamp>/)
#   RESULT_RE  grep -E pattern of log lines worth echoing after each step
# Provides: argument parsing (--parse --from --out -h), the run folder and its
# config.txt, steps 0 (check) and 1 (parse), and the helpers bold / die /
# want / run_step. The runner then does its own per-seed steps and summary.

# shellcheck disable=SC1091
source "$ROOT/config.sh"

CONFIG_VARS=(QUICK SEEDS MIN_RULES MAX_RULES MF_HIGH AC_THR ARITH LABEL_START TEST_FRAC CONF_MARGIN
             POP GENS TRAIN_SAMPLE LOSO_POP LOSO_GENS LOSO_TRAIN CSV_ROOT
             CARS_MAX_TERMS CARS_MIN_SUPPORT THFIS_MIN_SUPPORT)

# ---------------------------------------------------------------------------
# Arguments
# ---------------------------------------------------------------------------
STEPS=(check parse select loso finalize summary)
DO_PARSE=0; FROM=check; OUT=""
usage() { sed -n '2,/^set -euo/p' "$0" | sed '$d; s/^# \{0,1\}//'; exit "${1:-0}"; }
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
        grep -hE "$RESULT_RE" "$log" \
            | sed -E 's|^(\[finalize[^]]*\]) [^ ]+ |\1 |; s| -> .*||; s/^/      /' || true
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
    OUT="${OUT:-outputs/$METHOD/run_$(date +%Y-%m-%d_%H%M)$( [ "$QUICK" = 1 ] && echo _quick)}"
    [ -e "$OUT" ] && die "$OUT already exists -- pick another --out"
    mkdir -p "$OUT"
    COMMIT="$(git rev-parse --short HEAD 2>/dev/null || echo none)$(git diff --quiet 2>/dev/null || echo -dirty)"
    {
        echo "# $(basename "$0") settings ($(date '+%Y-%m-%d %H:%M'), commit $COMMIT)"
        for v in "${CONFIG_VARS[@]}"; do printf '%s="%s"\n' "$v" "${!v}"; done
        echo "# fixed: no hand-crafted rules used; identical (vector, label) events are weighted rows"
    } > "$OUT/config.txt"
fi
echo "run folder: $OUT"
echo "seeds: $SEEDS | rules $MIN_RULES-$MAX_RULES | MF_HIGH=$MF_HIGH | AC_THR=$AC_THR | ARITH=$ARITH | pop/gens $POP/$GENS (loso $LOSO_POP/$LOSO_GENS)"

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
    bold "1/5 parse  data/raw -> $CSV_ROOT"
    mkdir -p "$OUT/logs"
    run_step "parse_serial.sh" "$OUT/logs/parse.log" \
        env LOG_PATH="$ROOT/data/raw" OUTPUT_PATH="$ROOT/$CSV_ROOT" ./scripts/parse_serial.sh
    run_step "extract_launch.py" "$OUT/logs/launch.log" \
        "$PY" scripts/extract_launch.py data/raw data/attack_launch.csv
elif want parse; then
    bold "1/5 parse  (skipped -- use --parse to rebuild CSVs from logs)"
fi

if want check; then
    n_csv=$(find "$CSV_ROOT" -name '*.csv' | wc -l)
    echo "  CSVs   : $n_csv in $CSV_ROOT"
    [ "$n_csv" -gt 0 ] || die "no CSVs in $CSV_ROOT -- run with --parse"
    [ "$n_csv" -eq 72 ] || echo "  warning: expected 72 CSVs (mobile 3 rounds + static 1 round, x 3 atk counts x 6 scenarios)"
fi
