#!/usr/bin/env bash
#
# run_cars.sh -- CARS rule selection from start to end, in one command
# ===================================================================
#   0 check     venv, python libs, data/processed CSVs
#   1 parse     Cooja logs -> CSVs           (OFF unless --parse)
#   2 select    primary + round-holdout      methods/cars/run_real_selection.py
#   3 loso      leave-one-scenario-out S1-6  methods/cars/run_loso.py
#   4 finalize  best-F1 re-pick (2 splits)   methods/cars/finalize_selection.py
#   5 summary   SUMMARY.md                   scripts/summarize_run.py
#
# Settings live in config.sh (shared with run_thfis.sh).
#
# Usage:
#   ./run_cars.sh                          full run, settings from config.sh
#   QUICK=1 ./run_cars.sh                  ~30 s per seed smoke test
#   SEEDS="1 2 3 4 5" ./run_cars.sh        multi-seed; SUMMARY.md shows mean ± std
#   MAX_RULES=30 SEED=7 ./run_cars.sh      any setting can be overridden
#   ./run_cars.sh --parse                  also re-parse data/raw -> data/processed
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

METHOD=cars
RESULT_RE="data ceiling|knee base|^\[finalize\]"
# shellcheck disable=SC1091
source scripts/run_common.sh

COMMON=(--csv-root "$CSV_ROOT" --ac-thr "$AC_THR" --max-terms "$CARS_MAX_TERMS"
        --min-support "$CARS_MIN_SUPPORT" --conf-margin "$CONF_MARGIN"
        --mf-high "$MF_HIGH" --arith "$ARITH" --label-start "$LABEL_START" --min-rules "$MIN_RULES" --max-rules "$MAX_RULES")

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
            --test-frac "$TEST_FRAC" --seed "$seed" --split-seed "$SPLIT_SEED"
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
                --test-frac "$TEST_FRAC" --seed "$seed" --split-seed "$SPLIT_SEED"
        done
    fi
done

# ---------------------------------------------------------------------------
# 5. summary
# ---------------------------------------------------------------------------
bold "5/5 summary"
"$PY" scripts/summarize_run.py cars "$OUT"
