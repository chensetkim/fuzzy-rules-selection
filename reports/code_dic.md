# Code Dictionary — rule-selection pipeline

Per-file walkthroughs of the code in this repository. `README.md` says *where things are and
how to run them*; `reports/rules-selection-for-FERMAD.md` gives the *method and its
justification*; this file explains *how each file works and why it makes the choices it makes*.
The data-cleaning rules are collected in `reports/data-cleaning-rules.md`.

```
data/raw/*.log ──► scripts/parse_serial.py ──► data/processed/*.csv ─┐
              └──► scripts/extract_launch.py ──► data/attack_launch.csv ┤
                                                                       ▼
                                                        common/real_data.py   load, label, split, compress
                                                                       │
              common/fuzzy.py  (MFs, firing, Sugeno, int/float arithmetic)
                                                                       │
        ┌──────────────── CARS ────────────────┐      ┌──────────── T-HFIS ─────────────┐
        common/candidates.py  pool              │      methods/thfis/hfs_pipeline.py     │
        common/optimize.py    NSGA-II, knee     │      (unit pools, joint NSGA-II,       │
        common/report.py      tables, C export  │       inference, reporting, C export)│
        methods/cars/*.py     entry scripts     │      methods/thfis/*.py entry scripts  │
        └───────────────────────────────────────┘      └──────────────────────────────────┘
                                                                       │
        run_cars.sh / run_thfis.sh ── config.sh ── scripts/run_common.sh ── scripts/summarize_run.py
```

---

## Data preparation

### `scripts/parse_serial.py` — Cooja serial log → events CSV

The only code that reads raw firmware output; everything downstream reads the CSV it writes.

**Two-stage parsing.** `LOG` splits a Cooja line `<time> <mote_id> <serial text>` (the mote ID
bare or as `ID:<n>`); `EVT` then matches the firmware payload
`FUZZRID,DET,<src>,<R>,<Rhat>,<e>,<v1>..<v7>,<AC>,<ML>`. A line that carries `FUZZRID` but does
not match `EVT` is counted as malformed and reported — serial truncation or a changed `printf`,
not something to skip silently.

**`mote_id` vs `src`.** `mote_id` (from the Cooja line) is the node *doing* the observing;
`src` (from the payload) is the node *being* observed. Labels attach to `src`. Swapping them
fails silently, which is why `--atk-nodes` prints how many rows have an attacker as `src` and
warns at zero.

**Time.** The Cooja stamp is microseconds by default (`--time-unit us|ms`); the script writes
`sim_ms` (milliseconds) and `t = sim_ms // 1000` (seconds). Launch-time labels compare
`sim_ms`; a fixed `LABEL_START` compares `t`.

**Fail-loud range check.** Any $v_i$ outside 0–100 stops the script: a scale error would
otherwise distort every membership value without an error.

**Deduplication** drops only rows identical in **every** field (a replayed capture or mote
reboot) and reports how many. It never keys on `(sim_ms, mote_id, src)`, because one observer
can emit several genuine events for the same source within a millisecond. `--no-dedup` keeps
everything.

**Output schema** — 18 columns, fixed order:
`sim_ms,mote_id,src,R,Rhat,e,v1..v7,AC,ML,t,type,action`. `AC` is the firmware's own inference
output, kept for cross-checking `fuzzy.py`.

### `scripts/parse_serial.sh` — every log in a folder

Runs `parse_serial.py` on each `*.log` directly inside `LOG_PATH` (default `../data/raw`),
writing `<same name>.csv` into `OUTPUT_PATH` (default `../data/processed`). The names are kept,
so each CSV traces back to its log. Attacker IDs for the summary are read from each log's
`Starting 2H-FuzzRID attacker` boot lines. A failing log does not stop the others; failures are
listed at the end and the script exits non-zero.

### `scripts/extract_launch.py` — per-attacker launch times

Reads every log once, collecting each attacker's `[ATK-LAUNCHED]` line (stamp → `launch_ms`)
and the attackers that booted. Writes `data/attack_launch.csv` (`run, mote_id, launch_ms`,
where `run` is the file name without extension). It **stops with an error** if a booted attacker
has no launch line or one has two: a missing launch time would make that attacker's events
unlabellable. `./run_cars.sh --parse` runs it after `parse_serial.sh`.

---

## `common/real_data.py` — load, label, split, compress

Where ground truth is manufactured, so every rule here is a methodological claim.

**`_parse_name`** reads the four labels from the file name
(`<a>-<b>-<honest>-<atkcount>-<c>-S<k>-exp<id>[-mobile]-<round>.csv`): attacker count (4th
field), attack type, environment (`-mobile` present or not) and round. A name that does not
match raises an error rather than being guessed.

**`load_real_events(csv_root, label_start="launch", ...)`**

- *File order is fixed* — static first, then round, attacker count, name — because the row order
  seeds the primary split. This is the order the former folder tree produced, so splits are
  reproducible.
- Keeps `type == detection`, coerces $v_i$/`t`/`src`/`mote_id`/`sim_ms` to numbers and drops
  rows that do not parse.
- *Attacker set* per file from the attacker count (`ATK_NODES_BY_COUNT`; also in
  `data/attackers.txt`). See "Known gaps" in `data-cleaning-rules.md`: new topologies need this
  to come from the launch table instead.
- *Label*: with `label_start="launch"` (default), $y=1$ iff `src` is an attacker and
  `sim_ms` ≥ that attacker's launch (`load_launch_times`, from `data/attack_launch.csv`); a
  number applies one fixed start in seconds to every attacker (`300` = the former rule). A
  missing launch time for an attacker that appears as `src` raises an error.
- *Two row-dropping filters* (both default on): rows whose **observer** is an attacker
  (`drop_attacker_observers` — attackers do not run the IDS honestly) and rows observing an
  attacker **before its launch** (`drop_prelaunch_attacker_rows` — honest behaviour, so either
  label would be noise). Note that `is_atk_src` is recomputed after the first filter, because
  the frame has changed.
- Prints a summary (events, attack/benign, per scenario, per environment/round/attacker count)
  — the first thing to check in a run log.

**Splits.**

| Function | Train | Test |
|---|---|---|
| `stratified_scenario_split(ev, test_frac, seed)` | a shuffled 70 % of every scenario | the rest |
| `round_holdout_split(ev, "r3")` | all rounds but r3 | round r3 (mobile) |
| `scenario_holdout_split(ev, "S<k>")` | the other five attack types | S<k> |

The primary split shuffles rows *within* a scenario, so autocorrelated events land on both
sides; the other two splits measure how optimistic that is.

**`compress(ev)`** collapses events with the same $v_1..v_7$ **and** label into one row with
weight `w` = event count; returns `(X, y, w)`. Because the inference depends only on the
vector, every weighted quantity downstream equals the one on the raw events — lossless, and it
lets selection use the whole training partition cheaply. The weighted code was checked to
reproduce the unweighted code bit for bit on the same data.

**`vector_ceiling(ev)`** predicts each distinct vector as its majority label (ties → benign) and
returns that F1 and FPR: the best any classifier of $v_1..v_7$ can do on those events.

**`stratified_subsample(ev, n_target, seed)`** — optional sample, proportional within each
scenario × environment × attacker count × round cell, at least one event per cell. Only used
when `TRAIN_SAMPLE` > 0 (e.g. `QUICK=1`).

**`features_labels(ev)`** — unweighted `(X, y, groups)`, kept for ad-hoc analysis.

---

## `common/fuzzy.py` — the inference core

**`MFConfig(low=(20,50), med=(20,50,80), high=(50,80))`** — Low, Medium, High on 0–100, the same
sets as the firmware's `mu_L/mu_M/mu_H`. `memberships(X)` returns an `(n, 7, 3)` array; with
integer arithmetic it calls `_memberships_int`, which uses the firmware's truncating integer
division (`(dist * 100) / width`) on integer inputs and returns `k/100` so the rest of the code
is unchanged.

**`set_arithmetic("int" | "float")`** — a module-level switch read by `memberships` and
`sugeno_ac`. `int` (default) is bit-exact with `fuzzrid-fuzzy.c` (checked against its compiled C
functions); `float` is the continuous model. Entry scripts call it right after parsing
`--arith`.

**`firing_matrix(M, antecedents)`** — `(n_rows, n_rules)` min t-norm over the specified terms;
an all-don't-care rule fires at 0.

**`sugeno_ac(W, z, subset=None)`** — the weighted average. `int`: weights `rint(W*100)`,
$\lfloor\sum w z / (1+\sum w)\rfloor$ as the firmware; `float`: $\sum wz/(\sum w+0.01)$.

**Rule encoding** — antecedent = 7-tuple over {0 don't-care, 1 L, 2 M, 3 H}; consequent
$z \in \{0,25,50,75,100\}$. `rule_str` renders a rule as text.

---

## CARS (flat selection)

### `common/candidates.py` — the candidate pool

`build_pool(X, y, mf, max_terms=4, min_support=0.005, conf_margin=0.15, wm_max_rules=200, w=None)`:

1. `enumerate_antecedents(4)` — every antecedent with 1–4 specified features (3,990).
2. `wang_mendel_antecedents(M, 200, w)` — each row's strongest term per feature gives a 7-term
   cell; cells ranked by (weighted) occupancy, top 200.
3. Deduplicate, then `firing_matrix` once for all candidates.
4. `assign_consequents(W, y, w)` — confidence = firing-weighted share of attack events, support
   = mean firing strength; with weights the sums are `w @ W` (no copy of `W`); $z$ = nearest
   singleton to 100·conf, ties to the smaller.
5. Prune: `support >= min_support` and `|conf - 0.5| >= conf_margin`. Side effect: no kept rule
   can have $z = 50$.

Returns `antecedents, z, conf, support, names (G<i>(enum|wm)), W`. No hand-crafted rules exist.

### `common/optimize.py` — NSGA-II

- `f1_fpr(ac, y, ac_thr=65, w=None)` — confusion counts (weighted sums of `w` when given), F1,
  FPR, precision, recall.
- `RuleSelectionProblem` — objectives $(1-F_1,\ \mathrm{FPR},\ |S|/\text{max\_rules})$ on the
  training rows, constraints $\text{min\_rules} \le |S| \le \text{max\_rules}$; an empty subset
  gets $F=[1,1,0]$ and is infeasible.
- `random_population` — sparse random subsets (density 0.02). No seeding.
- `run_nsga2` — pymoo NSGA-II, uniform crossover 0.9, bit-flip $1/n$, duplicates eliminated.
- `knee_solution(F, w=(0.6,0.3,0.1))` — min–max normalise the training objectives, weighted sum,
  minimum. A preference-weighted choice, not a geometric knee.

### `common/report.py` — tables and C export

- `pareto_table` — one row per front member: train and test F1/FPR, test recall/precision, rule
  count, rule names (weighted by `w_tr` / `w_te`).
- `rules_listing` — human-readable rules with support and confidence.
- `export_c` — the selected base as the rule block of `fuzzrid_fuzzy_infer_ac()`: nested
  `min2()` per rule and the firmware's `num/den` loop with `den = 1`.

### `methods/cars/run_real_selection.py`

`run_one(tag, ev_train, ev_test, ...)`: optional sample (`--train-sample`, 0 = all) →
`compress` train and test → print sizes and the **data ceiling** → `build_pool` → test firing
matrix → `run_nsga2` → `pareto_front.csv` → knee base → `selected_rules.txt` (with the ceiling
line) and `selected_rules.c`. `main()` loads the corpus once and runs the primary and
round-holdout splits.

### `methods/cars/run_loso.py`

Imports `run_one` and runs it for each held-out attack type S1–S6 (smaller default NSGA-II
budget), then prints the per-fold table and the mean.

### `methods/cars/finalize_selection.py`

Rebuilds exactly the same pool (same split, seed, sample, MFs, arithmetic, labels), picks the
best test F1 within the rule budget (`pick_best`, ties within 0.002 → fewer rules), maps the
row's rule names back to a mask (asserting the count matches) and writes
`selected_rules_best_f1.{txt,c}`. It chooses using the **test** split; report the knee numbers as
the clean result.

---

## T-HFIS (hierarchical selection)

### `methods/thfis/hierarchy.py`

Only the layout: `RA_IN = [v1, v3, v4]`, `SI_IN = [v2, v5]`, `CX_IN = [v6, v7]` (as column
indices) and the input names per unit; TOP takes RA, SI, CX. No rules.

### `methods/thfis/hfs_pipeline.py`

- `build_unit_pool(X_local, y, mf, tag, w=...)` — full enumeration of the unit's antecedents,
  weighted certainty-grade consequents, pruning (support floor 0.01, margin 0.15).
- `build_all_pools(X, y, mf, w=...)` — the three layer-1 pools, then the TOP pool fitted against
  a *reference* RA/SI/CX: the layer-1 pools with all their rules on.
- `hfs_infer` — real two-layer inference for any mask (`split_mask` / `pool_dims` cut the joint
  mask into the four units).
- `HFSSelectionProblem` / `run_nsga2_hfs` — joint NSGA-II over `[RA|SI|CX|TOP]`, same objectives
  and constraints as CARS; each evaluation recomputes RA/SI/CX from the individual's own layer-1
  rules.
- `hfs_pareto_table`, `rules_listing_hfs` — as in CARS, per unit.
- `export_c_hfs(..., mf)` — writes a **complete, compilable `fuzzrid-fuzzy-hfs.c`**: MFs with the
  run's breakpoints, the integer Sugeno helper, one function per unit (`(void)` for unused
  inputs; `return 0` for a unit with no rules) and the two entry points declared in
  `c/fuzzrid-fuzzy-hfs.h`. Bit-exact with `hfs_infer` under `int` arithmetic. It is copied into
  the firmware unchanged — nothing is merged by hand.

### Entry scripts

`run_hfs_real_selection.py`, `run_hfs_loso.py` and `finalize_hfs_selection.py` mirror their CARS
counterparts (compress, ceiling, selection, best-F1 re-pick), using the functions above.

---

## Running

### `config.sh`

Every setting, shared by both runners, each overridable as `VAR=value ./run_cars.sh`: seeds,
rule budget, `MF_HIGH`, `AC_THR`, `ARITH`, `LABEL_START`, `TEST_FRAC`, `CONF_MARGIN`, NSGA-II
sizes and training sample (0 = all) for select and LOSO, `CSV_ROOT`, and the per-method pool
settings (`CARS_MAX_TERMS`, `CARS_MIN_SUPPORT`, `THFIS_MIN_SUPPORT`). `QUICK=1` swaps in tiny
sizes for a smoke test.

### `scripts/run_common.sh`

Sourced by both runners: parses `--parse`, `--from <step>`, `--out <dir>`, `-h`; creates
`outputs/<method>/run_<date>_<time>/` (never reusing an existing folder) and writes
`config.txt` with every setting and the git commit (`-dirty` if uncommitted); on `--from`,
reloads that `config.txt` so a resumed run uses the original settings. Step 0 checks the Python
libraries and counts the CSVs; step 1 (`--parse`) runs `parse_serial.sh` and
`extract_launch.py`. `run_step` logs a step to a file, echoes only the result lines, and on
failure prints the end of the log and stops.

### `run_cars.sh` / `run_thfis.sh`

Set `METHOD` and the lines to echo, source `run_common.sh`, then per seed run select, LOSO and
finalize with identical arguments (`--mf-high`, `--arith`, `--label-start`, rule budget, …), and
finally `summarize_run.py`.

### `scripts/summarize_run.py`

Reads every `seed_<s>/…/selected_rules*.txt` of a run and writes `SUMMARY.md`: rules, F1, FPR,
recall, precision and the data ceiling per split (mean ± std over seeds), and the LOSO mean F1.

### `scripts/install_lib.sh`

Creates the repo-root `.venv` if needed and installs `numpy`, `pandas`, `pymoo`.
