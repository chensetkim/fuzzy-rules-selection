# Data cleaning: methods and rules

How the Cooja logs in `data/raw/` become the training and test data used for rule selection.
The cleaning is **rule-based**: every rule is a fixed check derived from the simulation itself
(which motes are attackers, when each attacker launched, what the firmware prints), not a
statistical outlier filter tuned on the data.

**Principle.** A row is removed only when it is **invalid** (malformed, out of range, a
duplicate capture) or **cannot be labelled correctly** (reported by an attacker, or an
attacker observed before its launch). Hard but valid cases are kept, so that results are not
made to look better than the detector really is.

---

## 1. Parsing — is the record valid? (`scripts/parse_serial.py`)

| Rule | Action | Reason |
|---|---|---|
| A line must match the firmware format `FUZZRID,DET,<src>,<R>,<Rhat>,<e>,<v1>..<v7>,<AC>,<ML>` | Non-matching lines that carry the marker are skipped and counted (warning) | Serial truncation or a changed `printf` |
| Every $v_1..v_7$ must be within 0–100 | Stop with an error | A scale error would silently distort every membership value |
| Time unit | Cooja stamp (µs) → `sim_ms` (ms) → `t` (s); `--time-unit ms` if the Cooja version logs ms | A wrong unit shifts every label by a factor of 1000 |
| A row identical in **every** field to an earlier one | Dropped and counted | Replayed capture or mote reboot. Never deduplicate on (time, observer, source) alone: one observer can emit several genuine events for the same source within a millisecond |

## 2. Launch times — is the ground truth complete? (`scripts/extract_launch.py`)

| Rule | Action |
|---|---|
| Every attacker that boots (`Starting 2H-FuzzRID attacker`) must print exactly one `[ATK-LAUNCHED]` line | Stop with an error if a launch line is missing or appears twice |

Output: `data/attack_launch.csv` — one row per attacker and run (`run, mote_id, launch_ms`).

## 3. Loading — label noise and invalid evidence (`common/real_data.py`)

| Rule | Action | Reason |
|---|---|---|
| File name must match `<a>-<b>-<honest>-<atkcount>-<c>-S<k>-exp<id>[-mobile]-<round>.csv` | Stop with an error | Attacker count, attack type, environment and round are read from the name |
| Row type must be `detection` | Other rows dropped | Only IDS decisions are evidence |
| Non-numeric $v_i$, `t`, `src`, `mote_id`, `sim_ms` | Row dropped | Unparseable record |
| **Observer is an attacker** | Row dropped | Attackers do not run the IDS honestly; their reports are not evidence the deployed system would act on (no training distribution the deployed system never sees [Arp et al. 2022]) |
| **Observed attacker, before its own launch** | Row dropped, not labelled benign | The attacker behaves honestly then; either label would put noise into a region the rules cannot separate |
| Label | $y=1$ iff the observed node is an attacker **and** `sim_ms` ≥ that attacker's launch time; otherwise $y=0$ | Ground truth from the simulation, per attacker, to the millisecond (`LABEL_START=launch`; a number, e.g. `300`, applies one fixed start to every attacker as an ablation) |
| Duplicate runs | Byte-identical runs are kept only once in `data/` | A deterministic simulation rerun with the same seed is a copy, not a new repetition; keeping copies would count its events several times |

## 4. Compression — removing redundancy, not information (`compress()` in `common/real_data.py`)

| Rule | Action | Effect |
|---|---|---|
| Events with the same $v_1..v_7$ **and** the same label | Collapsed into one row weighted by its event count | Lossless: confidence, support, Wang–Mendel occupancy, F1 and FPR are identical to those on the individual events, so selection can use the whole training partition at low cost |

## 5. Deliberately **not** removed

| Kept | Reason |
|---|---|
| All-zero evidence vectors | The mote sees them too; removing easy benign cases would distort FPR |
| Repeated reports (same observer → source, same vector) | Each is a real decision the mote makes; with weighted rows they cost nothing |
| Events in the same second that differ in milliseconds | Real, separate evaluations |
| Attack events with no visible evidence yet | A real detection delay; removing them would overstate recall |
| Identical vectors that occur with both labels | They set the data's true limit; it is reported as the **data ceiling** (best F1 any classifier of $v_1..v_7$ can reach on that test set) instead of being hidden |
| Rare features (e.g. $v_7$, almost always zero) | $v_7$ is the two-hop forgery signal |

---

## Adding new Cooja data

1. Name each log `<a>-<b>-<honest>-<atkcount>-<c>-S<k>-exp<id>[-mobile]-<round>.log`
   (4th field = attacker count, `-mobile` absent = static, last number = round). Use a new
   `exp<id>`, and new round numbers when adding rounds to an existing setup.
2. Copy the logs into `data/raw/` and run `./run_cars.sh --parse` (parses the logs into
   `data/processed/` and rebuilds `data/attack_launch.csv`). All rules above then apply
   automatically.
3. Before selecting, check the start of `select.log`: the `[real_data]` event and attack/benign
   counts and the per-cell table (every scenario, environment, round and attacker count present,
   with a plausible attack share), the data ceiling per split, and that `t` ends near the
   simulated duration in seconds.

## Known gaps

- **Attacker IDs are fixed per attacker count** (`ATK_NODES_BY_COUNT` in `common/real_data.py`).
  A new topology with other attacker IDs or counts would be labelled wrongly without an error.
  Fix: take each run's attackers from `data/attack_launch.csv`.
- **Duplicate runs are not detected automatically.** Fix: a hash check over `data/raw/`.
- **Proposed `scripts/check_data.py`**, run by the check step: name pattern, booted attackers ==
  launch table, no identical runs, plausible `t` range, events per run, attack share and
  all-zero share per run, corpus data ceiling. It would also replace the fixed CSV-count
  warning in `scripts/run_common.sh`.
