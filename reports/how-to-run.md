# How to run rule selection

Everything runs from the repository root with one command per method. All settings live in
`config.sh` (shared by both methods); any of them can be overridden for one run as
`VAR=value ./run_cars.sh`.

## Before a run

1. **Commit first.** Every run writes `config.txt` with all settings and the git commit; with
   uncommitted changes the commit is marked `-dirty`, and the run cannot be tied to exact code.
2. **Python environment.** `./scripts/install_lib.sh` once (creates `.venv` with `numpy`,
   `pandas`, `pymoo`). The runners use `.venv` automatically.
3. **Data.** `data/processed/*.csv` and `data/attack_launch.csv` must exist. After adding or
   changing logs in `data/raw/`, add `--parse` (see `reports/data-cleaning-rules.md`).
4. **Machine load.** A full run keeps several cores busy. If Cooja batches are running on the
   same PC, both slow down; prefer a quiet PC or time slot. Never stop other people's processes.

## Commands

```bash
cd /home/kimpc/Github/fuzzy-rules-selection

QUICK=1 ./run_cars.sh                  # smoke test (tiny sample and NSGA-II budget)

./run_cars.sh                          # full length, one seed (42)
./run_thfis.sh

SEEDS="1 2 3 4 5" ./run_cars.sh        # full length, five seeds: SUMMARY.md gives mean ± std
SEEDS="1 2 3 4 5" ./run_thfis.sh

./run_cars.sh --parse                  # first rebuild data/processed and data/attack_launch.csv from data/raw
./run_cars.sh -h                       # usage
```

**Full length** = the `config.sh` defaults: population 150 × 250 generations for select,
finalize and every LOSO fold, the whole training partition (as weighted rows), integer
arithmetic, labels from each attacker's launch time. `SEEDS` are search seeds; the primary
70/30 split is fixed by `SPLIT_SEED=42`, so every seed is scored on the same test events.

**In the background** (keeps running after the terminal closes):

```bash
nohup env SEEDS="1 2 3 4 5" ./run_cars.sh  > cars_full.log  2>&1 &
nohup env SEEDS="1 2 3 4 5" ./run_thfis.sh > thfis_full.log 2>&1 &
tail -f cars_full.log
```

CARS and T-HFIS can run at the same time; they write to separate folders.

**Choosing the output folder:** `--out outputs/cars/<name>` (it must not exist yet); by default
`outputs/<method>/run_<date>_<time>/`.

## How long

On PC1 (Intel Core i7-11700, 16 threads, otherwise mostly idle) for one seed. CARS select was
measured; the rest is estimated from it (LOSO now uses the full 150 × 250 budget, about 3.9×
the work of the former 80 × 120):

| Step | CARS | T-HFIS |
|---|---|---|
| Select (primary + round-holdout) | 6.4 min (measured) | ≈ 21 min |
| LOSO (6 folds) | ≈ 17 min | ≈ 60 min |
| Finalize + summary | < 1 min | < 1 min |
| **One seed** | **≈ 24 min** | **≈ 82 min** |
| **Five seeds** | **≈ 2 h** | **≈ 7 h** |

Seeds run one after another inside one run. Peak memory ≈ 1.8 GB (CARS), ≈ 0.4 GB (T-HFIS).
Other load on the machine makes it slower.

## If a run stops

Resume from the step that was interrupted; the run's `config.txt` is reloaded, so the settings
stay identical:

```bash
./run_cars.sh --out outputs/cars/run_<date>_<time> --from loso      # steps: select, loso, finalize, summary
```

If a step fails, the runner stops and prints the last lines of that step's log
(`seed_<s>/logs/<step>.log`).

## What a run produces

```
outputs/<method>/run_<date>_<time>/
  config.txt            every setting + git commit
  SUMMARY.md            rules, F1, FPR, recall, precision, data ceiling per split; LOSO mean F1
  seed_<s>/
    primary/            pareto_front.csv, selected_rules.{txt,c}, selected_rules_best_f1.{txt,c}
    round_holdout/      same
    loso/S1..S6/        pareto_front.csv, selected_rules.{txt,c}
    logs/               select.log, loso.log, finalize_*.log
```

- **Knee base** (`selected_rules.*`) — chosen on training objectives only: the clean held-out
  result to report.
- **Best-F1 base** (`selected_rules_best_f1.*`) — chosen using the test split; report it as
  validation-selected.
- **Deploying:** CARS `selected_rules.c` is the rule block for `fuzzrid_fuzzy_infer_ac()` in
  `fuzzrid-fuzzy.c`; T-HFIS `selected_rules.c` is a complete `fuzzrid-fuzzy-hfs.c`
  (`reports/thfis-implement.md`). The firmware's membership functions must match `MF_HIGH` in
  `config.txt`.

## Reading the results

- Compare **round-holdout** and **LOSO** with **primary**: the gap shows how optimistic the
  primary split is.
- Every F1 should be clearly below its **ceiling F1**; a result at or near it suggests leakage.
- Look at **precision vs recall** in weak LOSO folds: which side fails (missed attacks or false
  alarms).
- With several seeds, the ± is optimiser variability on the same test events; a difference
  between settings matters only if it is larger than that spread.

## Comparison runs

Each changes one thing relative to the default, to measure its effect:

```bash
SEEDS="1 2 3 4 5" LABEL_START=300 ./run_cars.sh                                        # fixed 300 s labels
SEEDS="1 2 3 4 5" LABEL_START=300 TRAIN_SAMPLE=40000 LOSO_TRAIN=30000 ./run_cars.sh   # former setup
SEEDS="1 2 3 4 5" ARITH=float ./run_cars.sh                                           # continuous arithmetic
SEEDS="1 2 3 4 5" MF_HIGH=60,90 ./run_cars.sh                                         # earlier High set
```

Run the same with `./run_thfis.sh` to compare the methods under identical settings.
