#!/usr/bin/env bash
#
# run_thfis.sh -- T-HFIS (hierarchical) rule selection from start to end
# =====================================================================
#   0 check     venv, python libs, data/processed CSVs
#   1 parse     Cooja logs -> CSVs           (OFF unless --parse)
#   2 select    primary + round-holdout      methods/thfis/run_hfs_real_selection.py
#   3 loso      leave-one-scenario-out S1-6  methods/thfis/run_hfs_loso.py
#   4 finalize  best-F1 re-pick (2 splits)   methods/thfis/finalize_hfs_selection.py
#   5 summary   SUMMARY.md                   scripts/summarize_run.py
#
# Settings live in config.sh (shared with run_cars.sh), so both methods run
# with the same rule budget, MFs, threshold, splits, seeds and NSGA-II sizes.
#
# Usage:
#   ./run_thfis.sh                         full run, settings from config.sh
#   QUICK=1 ./run_thfis.sh                 ~30 s per seed smoke test
#   SEEDS="1 2 3 4 5" ./run_thfis.sh       multi-seed; SUMMARY.md shows mean ± std
#   MAX_RULES=30 SEED=7 ./run_thfis.sh     any setting can be overridden
#   ./run_thfis.sh --parse                 also re-parse data/raw/logs -> data/processed
#   ./run_thfis.sh --out outputs/thfis/run_X --from loso
#                                          resume an earlier run from a step
#                                          (its config.txt is reused)
#
# Each run writes to its own folder and never overwrites earlier results:
#   outputs/thfis/run_<date>_<time>/
#     config.txt   SUMMARY.md
#     seed_<s>/primary/ round_holdout/ loso/S1..S6/ logs/
#
set -euo pipefail
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

METHOD=thfis
RESULT_RE="knee base|hand-crafted T-HFIS .* on this test|^\[finalize-hfs\]"
# shellcheck disable=SC1091
source scripts/run_common.sh

COMMON=(--csv-root "$CSV_ROOT" --ac-thr "$AC_THR"
        --min-support "$THFIS_MIN_SUPPORT" --conf-margin "$CONF_MARGIN"
        --mf-high "$MF_HIGH" --min-rules "$MIN_RULES" --max-rules "$MAX_RULES")

# ---------------------------------------------------------------------------
# 2-4. per seed: select, loso, finalize
# ---------------------------------------------------------------------------
for seed in $SEEDS; do
    S="$OUT/seed_$seed"; mkdir -p "$S/logs"

    if want select; then
        bold "2/5 select  seed $seed  (primary + round-holdout)"
        run_step "run_hfs_real_selection" "$S/logs/select.log" \
            "$PY" methods/thfis/run_hfs_real_selection.py "${COMMON[@]}" --out-root "$S" \
            --pop "$POP" --gens "$GENS" --train-sample "$TRAIN_SAMPLE" \
            --test-frac "$TEST_FRAC" --seed "$seed"
    fi

    if want loso; then
        bold "3/5 loso  seed $seed  (S1..S6)"
        run_step "run_hfs_loso" "$S/logs/loso.log" \
            "$PY" methods/thfis/run_hfs_loso.py "${COMMON[@]}" --out-root "$S/loso" \
            --pop "$LOSO_POP" --gens "$LOSO_GENS" --train-sample "$LOSO_TRAIN" --seed "$seed"
    fi

    if want finalize; then
        bold "4/5 finalize  seed $seed  (best-F1 within $MIN_RULES-$MAX_RULES rules)"
        for split in primary round_holdout; do
            [ -f "$S/$split/pareto_front.csv" ] || die "$S/$split/pareto_front.csv missing -- run from 'select'"
            # Same seed / train-sample / test-frac as select, or the pools won't match.
            run_step "finalize $split" "$S/logs/finalize_$split.log" \
                "$PY" methods/thfis/finalize_hfs_selection.py "${COMMON[@]}" --split "$split" \
                --out-dir "$S/$split" --train-sample "$TRAIN_SAMPLE" \
                --test-frac "$TEST_FRAC" --seed "$seed"
        done
    fi
done

# ---------------------------------------------------------------------------
# 5. summary
# ---------------------------------------------------------------------------
bold "5/5 summary"
"$PY" scripts/summarize_run.py thfis "$OUT"
