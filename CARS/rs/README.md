# 2H-FuzzRID Offline Rule-Selection Pipeline

Answers the reviewer question *"why these 18 rules and not others?"* by
replacing "expert choice" with a reproducible procedure: **candidate
generation (Wang–Mendel + bounded enumeration) → multi-objective NSGA-II
subset selection → comparison against the taxonomy-derived base R1–R18.**

## Pipeline

```
results/raw/csv/*.csv  (parse_serial.py output, one row per IDS event)
        │
        ▼
 data.py         label: y=1 iff src ∈ attackers AND t ≥ ATK_START_S
        │        (same convention as compute_metrics.py)
        ▼
 candidates.py   candidate pool =
                   • bounded enumeration: all antecedents with ≤4 terms
                     (Σₖ C(7,k)·3ᵏ = 3,990 rules)
                   • Wang–Mendel full-antecedent rules from data cells
                   • the deployed expert base R1–R18 (always included)
                 consequents by Ishibuchi certainty grade
                 conf(r) = Σ_{y=1} w_r / Σ w_r → nearest {0,25,50,75,100}
                 pruned by min support and confidence margin
        │
        ▼
 optimize.py     NSGA-II over binary rule-inclusion chromosomes
                 objectives (min): 1−F1, FPR, rule count
                 constraint: |S| ≤ max_rules (Z1 RAM/flash budget)
                 expert base seeded into generation 0
        │
        ▼
 report.py       pareto_front.csv  · selected_rules.txt
                 selected_rules.c  (drop-in for fuzzrid_fuzzy_infer_ac)
                 overlap_report.txt (Jaccard vs R1–R18 per Pareto base)
```

## Usage

```bash
pip install numpy pandas pymoo

python3 run_selection.py  results/raw/csv/  results/rule_selection/ \
    --atk-nodes 33,34,35 \        # or --atk-id-start 33
    --atk-start-s 300 \           # FUZZRID_T_WARM_S
    --ac-thr 65 \                 # FUZZRID_TAU_Q_PCT
    --max-rules 30 --pop 120 --gens 200 --seed 42
```

For the mote-ID layout where attackers are 5–10 (SimFile-A logs), use
`--atk-nodes 5,6,7,8,9,10`. To evaluate against the pre-March-2026
membership functions, pass `--mf-high 50,80`.

Multi-seed reproducibility (for the statistical-reliability requirement):
run with `--seed 1..10` and report the variation of the Pareto knee.

## Outputs

- **pareto_front.csv** — every non-dominated rule base with train/test
  F1, FPR, recall, precision, rule count, and overlap with R1–R18.
- **selected_rules.txt** — the knee-point base, human readable, with
  per-rule support and confidence.
- **selected_rules.c** — the same base emitted as the integer-arithmetic
  rule block of `fuzzrid_fuzzy_infer_ac()` (min t-norm via `min2`,
  ε=1 Sugeno weighted average) — deployable on Z1/MSP430 unchanged.
- **overlap_report.txt** — expert-rule containment across the whole front.

## How to use the result in the manuscript (§4.4)

Two outcomes, both publishable:

1. **Expert base on/near the Pareto front** → report that the
   taxonomy-derived base is empirically non-dominated (or within the
   front's F1/FPR envelope at equal rule count). The manual derivation
   (§4.4.2) explains rule *structure*; the optimization certifies rule
   *selection*.
2. **Optimizer finds a dominating base** → adopt it (via
   `selected_rules.c`), and the methodology becomes fully systematic:
   "candidate generation + evolutionary multi-objective selection", with
   R1–R18 reported as the expert prior that seeded the search.

Either way, cite: Wang & Mendel (1992) for rule generation from data;
Ishibuchi, Murata & Türkşen (1997) / Ishibuchi & Yamamoto (2004) for
GA-based fuzzy rule selection with accuracy–complexity objectives;
Deb et al. (2002) for NSGA-II.

## Guardrails (write these into the paper's limitations/validity)

- Selection uses **train split only**; the reported comparison is on the
  held-out split (per-scenario stratified so all six attack variants
  appear in both). For stronger evidence, do leave-one-scenario-out:
  train on five variants, test on the sixth, showing selected rules
  generalise across attack types.
- MF breakpoints are held fixed during rule selection. Do **not** tune
  breakpoints and rules on the same split in the same run, or the
  circular-threshold critique reappears one level down. If you later add
  GA/PSO breakpoint tuning, nest it: outer CV fold → tune → evaluate.
- Labels come from simulation ground truth (attacker mote IDs), so the
  learned consequents inherit Cooja's single-topology scope — state this
  alongside the existing single-topology limitation.

## Files

| File | Purpose |
|---|---|
| `parse_serial.py` | Cooja serial log → events CSV (see `fuzzy_rules_selection.md` §12) |
| `fuzzy.py` | MFs (firmware-faithful, [60,90] High default), rule encoding, vectorised Sugeno AC, canonical R1–R18 |
| `data.py` | Event CSV loader + labelling (compute_metrics.py convention) |
| `candidates.py` | WM + enumeration candidate pool, certainty-grade consequents, pruning |
| `optimize.py` | NSGA-II (pymoo), expert-seeded population, F1/FPR/size objectives |
| `report.py` | Pareto table, overlap stats, C export |
| `run_selection.py` | CLI entry point |
| `make_synth.py` | Synthetic-data smoke test (`python3 make_synth.py && python3 run_selection.py synth_csv out/`) |
