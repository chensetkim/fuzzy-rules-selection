# Fuzzy rule selection for FERMAD

Offline, data-driven selection of the FERMAD fuzzy rule base from Cooja simulation logs.
Two methods are implemented: **CARS** (flat NSGA-II selection, the adopted method) and
**T-HFIS** (hierarchical selection, evaluated as an alternative).

## Layout

```
common/           code shared by both methods
  fuzzy.py          membership functions + Sugeno inference
  candidates.py     candidate rule-pool generation
  optimize.py       NSGA-II selection, knee point, F1/FPR
  report.py         Pareto table, rule listing, C export, expert overlap
  real_data.py      loader, labelling and splits for data/processed/

methods/
  cars/             flat selection: run_real_selection, run_loso, finalize_selection
  thfis/            hierarchical: hierarchy, hfs_pipeline, run_hfs_real_selection,
                    run_hfs_loso, finalize_hfs_selection
    c/              Contiki C implementation (fuzzrid-fuzzy-hfs.c/.h)

scripts/          parse_serial.py/.sh (log -> CSV), install_lib.sh,
                  run_common.sh (shared runner plumbing), summarize_run.py (SUMMARY.md)

config.sh         settings shared by run_cars.sh and run_thfis.sh

data/
  raw/logs/{mobile,static}/r{1,2,3}/{3,6,9}/*.log    Cooja serial logs
  processed/{mobile,static}/r{1,2,3}/{3,6,9}/*.csv   parsed event CSVs (input to both methods)
  archive/backup/   local backup zip of the CSVs (untracked)

outputs/
  cars/run_<date>_<time>/    one folder per run_cars.sh run (config.txt, SUMMARY.md, seed_<s>/)
  thfis/run_<date>_<time>/   one folder per run_thfis.sh run
  legacy_2026-09/            results quoted in reports/, made with the old settings (see its README)

reports/          write-ups and results (start with offline-rule-selection-methods.md)
```

## Running

**Start to end:** `./run_cars.sh` (CARS) and `./run_thfis.sh` (T-HFIS) each run
check → select → LOSO → finalize → SUMMARY.md into a new `outputs/<method>/run_<date>_<time>/`.
Both read their settings from **`config.sh`** (rule budget, MFs, threshold, split, seeds,
NSGA-II sizes), so the two methods always run with the same values; only the per-method
pool settings (`CARS_*`, `THFIS_*`) differ. `QUICK=1 ./run_cars.sh` is a ~30 s per seed
smoke test, `SEEDS="1 2 3 4 5"` a multi-seed run, `--parse` rebuilds the CSVs from the logs,
and `-h` shows the usage. The individual steps below remain available.

Python commands are run **from the repo root**; their default paths (`data/processed`,
`outputs/<method>`) are relative to it. Shell scripts `cd` into their own folder and can be
run from anywhere.

```bash
./scripts/install_lib.sh                       # once: numpy, pandas, pymoo into .venv
source .venv/bin/activate

# Cooja logs -> CSVs (one folder at a time; see the script header for a loop)
LOG_PATH=../data/raw/logs/mobile/r1/6 OUTPUT_PATH=../data/processed/mobile/r1/6 ./scripts/parse_serial.sh

# CARS
python3 methods/cars/run_real_selection.py     # -> outputs/cars/{primary,round_holdout}/
python3 methods/cars/run_loso.py               # -> outputs/cars/loso/S1..S6/
python3 methods/cars/finalize_selection.py --split primary --out-dir outputs/cars/primary

# T-HFIS
python3 methods/thfis/run_hfs_real_selection.py  # -> outputs/thfis/{primary,round_holdout}/
python3 methods/thfis/run_hfs_loso.py            # -> outputs/thfis/loso/S1..S6/
```

Use `--pop 20 --gens 5 --train-sample 3000 --out-root <tmp>` for a quick check.
Full instructions: [reports/rules-selection-for-FERMAD.md §14](reports/rules-selection-for-FERMAD.md).
