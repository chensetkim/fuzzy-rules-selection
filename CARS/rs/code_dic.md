# Code Dictionary — rule-selection pipeline

Per-file walkthroughs of `CARS/rs/`. `README.md` describes *what the pipeline
does*; this file describes *how each script works and why it makes the choices
it makes*. One section per file, added as they are documented.

---

## `parse_serial.py` — Cooja serial log → events CSV

The bridge between the Cooja simulation and the rest of the pipeline. It is the
only script that touches raw firmware output; everything downstream reads the
CSV it produces.

```
Contiki firmware printf
        │   "FUZZRID,DET,<src>,<R>,<Rhat>,<e>,<v1..v7>,<AC>,<ML>"
        ▼
Cooja test script                TIMEOUT(1800000);
        │   log.log(time + " " + id + " " + msg + "\n")
        ▼
sim.log                          "<time> <mote_id> <serial text>"
        │
        ▼
parse_serial.py  ───────────────►  S1_decrease_jump_run1.csv
        │
        ▼
data.py → candidates.py → optimize.py → report.py
```

### Invocation

```bash
python3 parse_serial.py sim.log ../sample_csv/S1_decrease_jump_run1.csv \
    [--time-unit us|ms] [--atk-nodes 5,6,7,8,9,10] [--no-dedup]
```

| Argument | Meaning |
|---|---|
| `log` | captured Cooja log (positional) |
| `out_csv` | destination CSV; parent directories are created |
| `--time-unit` | unit of the Cooja script's `time` variable, `us` (default) or `ms` |
| `--atk-nodes` | attacker mote IDs — **summary/sanity output only**, labelling happens in `data.py` |
| `--no-dedup` | keep byte-identical duplicate rows |

The output filename matters downstream: `data.py` takes the **scenario label
from the filename prefix before the first `_`** (`S1_decrease_jump_run1.csv` →
scenario `S1`), and the split is stratified on it. Name files accordingly.

### Two-stage parsing

Parsing is deliberately split into two regexes, because two different producers
own the two halves of a log line:

- **`LOG`** (`^\s*(\d+)\s+(\d+)\s+(.*)$`) strips the wrapper Cooja adds:
  timestamp, emitting mote, remaining payload. Owned by the Cooja test script.
- **`EVT`** matches the firmware's detection marker inside that payload: <br>
>`FUZZRID,DET,src,R,Rhat,e,v1..v7,AC,ML`. 
  
  Owned by the firmware `printf`.

**If you change the firmware `printf`, you must change `EVT`.** The comment
directly above the pattern records the `printf` it was written against; keep the
two in sync or the parser silently yields zero rows.

`R`, `Rhat` and `e` are matched as `-?\d+` (signed — `e` is a residual and can go
negative); `v1..v7`, `AC`, `ML` are unsigned.

### `mote_id` vs `src` — the easiest mistake to make

| Column | Source | Meaning |
|---|---|---|
| `mote_id` | Cooja wrapper | the **observer** — which mote emitted the line |
| `src` | firmware payload | the **observed** — which node the detection is about |

`data.py` labels on `src ∈ attackers` and, when attacker IDs are known, drops
rows *emitted by* attackers (`mote_id ∈ attackers`). Swapping the two inverts
both operations. The `--atk-nodes` check at the end of `main()` exists precisely
to catch this: if no row has `src` in the attacker set, it warns that either the
attacker list or the `src`/`mote_id` order in `EVT` is wrong.

### Time: two columns, one unit trap

```python
sim_ms = int(stamp) // 1000 if time_unit == "us" else int(stamp)
...
"t": sim_ms // 1000,        # SECONDS
```

- `sim_ms` — milliseconds, carried for traceability.
- `t` — **seconds**, and load-bearing: `data.py` labels attack rows with
  `t >= atk_start_s` (e.g. 300 s = `FUZZRID_T_WARM_S`).

Cooja's `time` is microseconds in most versions, hence the `us` default — but
**verify it once for your Cooja build**. If the unit is wrong by 1000×, every
row lands on one side of the attack window and the labels are uniformly wrong
rather than obviously broken. The `[parse] t range a..b s` line in the summary
is the cheap check: it should span your simulation duration in seconds.

### Fail-loud range check

```python
for k in V:
    if not 0 <= int(d[k]) <= 100:
        raise ValueError(...)
```

Raises rather than warns. The fuzzy membership functions in `fuzzy.py` assume
features are normalised to 0..100 on the mote; an un-normalised raw value parses
fine as an integer and would silently produce meaningless memberships all the
way through candidate generation and NSGA-II. Cheapest place to catch a firmware
scaling bug is here.

### Deduplication

The dedup key is the **entire row**, not `(sim_ms, mote_id, src)`. This is
intentional and documented in the `parse()` docstring: one observer legitimately
emits several detection events for the same source within a single millisecond,
carrying different evidence vectors. Keying on the triple would silently discard
real observations. Only byte-identical rows are dropped — the signature of a
replayed capture or a mote reboot re-emitting its buffer.

### Output schema

```
sim_ms,mote_id,src,R,Rhat,e,v1..v7,AC,ML,t,type,action
```

Fixed by `data.py`, which reads only `type` (filters `== "detection"`),
`mote_id`, `src`, `t` and `v1..v7`. The rest are carried for traceability, with
one column worth calling out:

> **`AC` is the firmware's own inference output.** Running `fuzzy.py`'s Sugeno
> inference over the same `v1..v7` and comparing against `AC` cross-checks the
> Python model against the deployed C implementation. If they diverge, the
> offline rule selection is optimising something the mote does not actually
> compute.

`action` is written empty; `type` is always `detection` (the parser only ever
emits detection events).

### Diagnostics

All three are sanity assertions in disguise:

- `[warn] N lines carried the marker but did not match EVT` — the `FUZZRID`
  string was present but the shape was wrong: serial truncation, or `printf`
  drift away from `EVT`. A nonzero count means you are losing events.
- `[warn] dropped N fully-identical duplicate rows` — replayed capture or mote
  reboot.
- `no detection events parsed` (exit 1) — `LOG` or `EVT` no longer matches the
  log at all.
- `[parse] N events → ... | t range ... | observers=... sources=...` — the
  headline check. Wrong observer/source counts point at topology or ID-layout
  mismatches.

### Contract

Full specification in `fuzzy_rules_selection.md` §12.

---

## `data.py` — event CSVs → labelled feature matrix

Consumes the CSVs `parse_serial.py` writes and produces the `(X, y)` that
`candidates.py` and `optimize.py` train on. It is where **ground truth is
manufactured**, so every filter in it is a methodological claim that belongs in
the paper, not an implementation detail.

Three public functions, called in this order by `run_selection.py`:

```
load_events_dir(csv_dir, ...)          → ev : DataFrame  (all events, labelled)
train_test_split_by_scenario(ev, ...)  → (tr, te)
features_labels(tr) / (te)             → X : float64[n,7], y : int8[n], groups
```

### The labelling rule

```
y = 1  if  src ∈ attacker set  AND  t ≥ atk_start_s
y = 0  otherwise
```

This is deliberately **the same convention as `compute_metrics.py`**, the script
that produces the online results in the manuscript. Keeping the two identical is
what makes the offline rule-selection numbers comparable to the deployed
system's numbers; if they diverge, the comparison is meaningless.

The attacker set is specified one of two ways, and the choice propagates through
two separate filters:

| Mode | Attacker source test | Attacker observer test |
|---|---|---|
| `atk_nodes={5,…,10}` (explicit) | `src.isin(atk_nodes)` | `mote_id.isin(atk_nodes)` |
| `atk_id_start=33` (ID convention) | `src >= atk_id_start` | `mote_id >= atk_id_start` |

Explicit `atk_nodes` wins when given. The ID-convention fallback exists for the
topology where attackers occupy the high ID range; the SimFile-A layout
(attackers 5–10) sits *inside* the benign range and therefore **must** use
`--atk-nodes`. Using the default `atk_id_start=33` on a 5–10 layout produces
`y=0` everywhere — no crash, just a silently degenerate dataset. The
`[data] ... attack=N benign=M` line in `run_selection.py` is the check.

### Two row-dropping filters — both are methodological positions

```python
if drop_attacker_observers:          # default True
    ev = ev[~ev["mote_id"].isin(atk_nodes)]
...
if drop_prelaunch_attacker_rows:     # default True
    ev = ev[~(is_atk_src & ~in_window)]
```

**1. Rows emitted *by* attacker motes are dropped.** An attacker does not run
the IDS, so its serial output is not an observation — it is noise from a node
that, in the real deployment, would not be reporting at all. Keeping these rows
would train the rule base on evidence vectors that can never occur in the field.

**2. Attacker-sourced rows *before* the attack launches are dropped, not
labelled benign.** During warm-up (`t < atk_start_s`, e.g. 300 s =
`FUZZRID_T_WARM_S`) the attacker is behaving honestly. Labelling those rows
`y=0` would be defensible but injects label noise: the node *is* an attacker,
its neighbourhood statistics may already be drifting, and the ground truth is
genuinely ambiguous. Dropping them keeps the negative class clean.

Note the asymmetry, which is intentional: **benign** nodes' pre-launch rows are
kept as `y=0`. Only the ambiguous attacker-pre-launch rows go.

Both filters are keyword arguments defaulting to `True`, so the effect of
turning them off is one call away if a reviewer asks for the ablation.

### Why `is_atk_src` is recomputed

```python
is_atk_src = ev["src"].isin(atk_nodes)
if drop_attacker_observers:
    ev = ev[~ev["mote_id"].isin(atk_nodes)]
    is_atk_src = ev["src"].isin(atk_nodes)   # ← recomputed, not reused
```

The mask is built before the filter, then the filter shortens `ev`. A stale
boolean Series still carries the *old* index, so reusing it would misalign
against the filtered frame. Recomputing after the drop is the fix — not
redundancy.

### Silent coercion

```python
ev[c] = pd.to_numeric(ev[c], errors="coerce")
ev = ev.dropna(subset=V_COLS + ["t", "src", "mote_id"])
```

Unparseable values in `v1..v7`, `t`, `src` or `mote_id` become `NaN` and the row
disappears **without a count or a warning** — the opposite of `parse_serial.py`,
which raises on out-of-range features and prints a tally of malformed lines. In
a clean pipeline nothing should reach here that `parse_serial.py` let through,
so this is a belt-and-braces guard against hand-edited CSVs. If event counts ever
look low, this is a place to instrument.

Missing `v1..v7` **columns** do raise (`ValueError: {fn}: missing columns …`); it
is only bad *values* that vanish quietly.

### Scenario labels come from filenames

```python
df["scenario"] = fn.split("_")[0]
```

`S1_decrease_jump_run1.csv` → scenario `S1`. This is the only place scenario
identity enters the pipeline, and it drives the stratified split below. **Rename
a file carelessly and you change the experimental design** — e.g. dropping the
prefix collapses every run into one scenario named after whatever precedes the
first underscore.

### `train_test_split_by_scenario`

Splits **within** each scenario rather than across scenarios, so all six attack
variants appear in both train and test. This is required by the pipeline's
premise: rule selection must see every variant, or the selected base is tuned to
a subset of the attack taxonomy.

```python
for _, grp in ev.groupby("scenario"):
    idx = grp.index.to_numpy().copy()
    rng.shuffle(idx)                       # uniform random, seeded
    cut = int(len(idx) * (1.0 - test_frac))
```

Two things worth being precise about:

- Despite the docstring's phrase "chronologically-shuffled", the split is a
  **uniform random shuffle within scenario** — there is no temporal ordering in
  it. Consecutive events from the same observer/source pair are highly
  correlated, so a random split lets near-duplicate rows straddle train and test.
  This inflates held-out scores relative to a temporal or leave-one-scenario-out
  split. `README.md`'s guardrail — "for stronger evidence, do
  leave-one-scenario-out" — is exactly the fix, and this is the function it
  would replace.
- `ev.loc[sorted(tr_idx)]` is label-based indexing, which is safe only because
  `load_events_dir` ends with `reset_index(drop=True)`. Passing in a filtered
  frame that has not been re-indexed would misbehave.

`seed` (default 42) makes the split reproducible; `run_selection.py` threads the
same `--seed` into NSGA-II, so a multi-seed sweep varies split *and* search
together — which is what you want for the reliability claim in `README.md`
("run with `--seed 1..10` and report the variation of the Pareto knee").

### `features_labels`

```python
X = ev[V_COLS].to_numpy(dtype=np.float64)   # (n, 7), 0..100
y = ev["y"].to_numpy(dtype=np.int8)         # (n,)
groups = ev["scenario"].to_numpy()          # (n,)
```

Column order is fixed by `V_COLS` and must match `fuzzy.py`'s feature ordering —
`X[:, i]` is `v{i+1}` everywhere downstream.

`groups` is returned for grouped cross-validation but `run_selection.py`
currently discards it (`X_tr, y_tr, _ = features_labels(tr)`). It is the hook a
leave-one-scenario-out evaluation would use.

### Defaults to double-check per experiment

| Parameter | Default | Must match |
|---|---|---|
| `atk_id_start` | `33` | your mote-ID layout — **wrong for the 5–10 layout** |
| `atk_start_s` | `300` | `FUZZRID_T_WARM_S` in the firmware |
| `test_frac` | `0.3` (via `run_selection.py`) | — |
| `seed` | `42` | — |
