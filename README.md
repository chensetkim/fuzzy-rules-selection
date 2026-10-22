# Fuzzy rule selection for EF-RMAD

Offline, data-driven selection of the EF-RMAD fuzzy rule base from Cooja simulation logs.
Two methods are implemented: **CARS** (flat NSGA-II selection, the adopted method) and
**T-HFIS** (hierarchical selection, evaluated as an alternative).

## Layout

```
common/           code shared by both methods
  fuzzy.py          membership functions + Sugeno inference
  candidates.py     candidate rule-pool generation
  optimize.py       NSGA-II selection, knee point, F1/FPR
  report.py         Pareto table, rule listing, C export, expert overlap
  data.py           loader for a flat folder of CSVs (synthetic/sample pipeline)
  real_data.py      loader for the real corpus in data/processed/
  make_synth.py     synthetic CSV generator (smoke tests)

methods/
  cars/             flat selection: run_real_selection, run_loso, finalize_selection,
                    run_selection(.sh), run_full_process.sh
  thfis/            hierarchical: hierarchy, hfs_pipeline, run_hfs_real_selection,
                    run_hfs_loso, run_hfs_eval, finalize_hfs_selection
    c/              Contiki C implementation (fuzzrid-fuzzy-hfs.c/.h)

scripts/          data preparation: parse_serial.py/.sh (log -> CSV), install_lib.sh

data/
  raw/logs/{mobile,static}/r{1,2,3}/{3,6,9}/*.log    Cooja serial logs
  processed/{mobile,static}/r{1,2,3}/{3,6,9}/*.csv   parsed event CSVs (input to both methods)
  samples/          small sample CSVs + sim.log for the single-log pipeline
  archive/          zipped snapshots

outputs/
  cars/   primary/ round_holdout/ loso/S1..S6/  synthetic/  by_attackers/a3,a6,a9/
  thfis/  primary/ round_holdout/ loso/S1..S6/

reports/          write-ups and results (start with offline-rule-selection-methods.md)
archive/          old/unused files kept for reference
```

## Running

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
Full instructions: [reports/rules-selection-for-EF-RMAD.md §14](reports/rules-selection-for-EF-RMAD.md).

> `outputs/cars/by_attackers/a3,a6,a9` came from the old `Data/out/` folder; its origin
> (which script and settings) is not recorded.
