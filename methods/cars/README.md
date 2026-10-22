# CARS — flat offline rule selection for FERMAD

Selects the FERMAD rule base from data alone: **candidate generation
(Wang–Mendel + bounded enumeration) → multi-objective NSGA-II subset
selection**. No hand-crafted rules are used anywhere: not in the pool, not in
the initial population, and not as a built-in baseline.

Run everything with `./run_cars.sh` from the repo root (settings in `config.sh`).

## Pipeline

```
data/processed/{mobile,static}/r*/{3,6,9}/*.csv   (scripts/parse_serial.py output)
        │
        ▼
 common/real_data.py  label: y=1 iff src ∈ attackers AND t ≥ 300 s
                      splits: primary (70/30 per scenario), round-holdout (mobile r3),
                      leave-one-scenario-out (S1..S6)
        ▼
 common/candidates.py candidate pool, purely data-driven =
                        • bounded enumeration: all antecedents with ≤4 terms
                          (Σₖ C(7,k)·3ᵏ = 3,990 rules)
                        • Wang–Mendel full-antecedent rules from data cells
                      consequents by Ishibuchi certainty grade
                      conf(r) = Σ_{y=1} w_r / Σ w_r → nearest {0,25,50,75,100}
                      pruned by min support and confidence margin
        ▼
 common/optimize.py   NSGA-II over binary rule-inclusion chromosomes
                      objectives (min): 1−F1, FPR, rule count / max_rules
                      constraint: min_rules ≤ |S| ≤ max_rules
                      random initial population
                      scored with the mote's integer arithmetic (ARITH=int, default):
                      uint8 memberships, integer min, AC = ⌊Σw·z / (1+Σw)⌋, bit-exact
                      with fuzzrid-fuzzy.c; ARITH=float gives the continuous model
        ▼
 common/report.py     pareto_front.csv · selected_rules.txt · selected_rules.c
```

## Outputs (per split)

- **pareto_front.csv** — every non-dominated rule base with train/test F1, FPR,
  recall, precision and rule count.
- **selected_rules.txt** — the knee-point base, human readable, with per-rule
  support and confidence.
- **selected_rules.c** — the same base as the integer-arithmetic rule block of
  `fuzzrid_fuzzy_infer_ac()` (min t-norm via `min2`, ε=1 Sugeno weighted average).
- **selected_rules_best_f1.{txt,c}** — best test-F1 base within the rule budget
  (`finalize_selection.py`).

## Guardrails (state these in the paper's limitations/validity)

- Selection uses the **train split only**; reported metrics are on the held-out split.
  Round-holdout and LOSO check generalisation to an unseen simulation repetition and
  to an unseen attack type.
- `finalize_selection.py` picks by **test** F1, so report the knee-point numbers as the
  clean held-out result.
- MF breakpoints are fixed during selection. Do not tune breakpoints and rules on the
  same split; nest any breakpoint tuning inside an outer CV fold.
- Labels come from simulation ground truth (attacker mote IDs), so the learned
  consequents inherit Cooja's topology scope.

## Files

| File | Purpose |
|---|---|
| `run_real_selection.py` | Primary + round-holdout selection |
| `run_loso.py` | Leave-one-scenario-out selection (S1..S6) |
| `finalize_selection.py` | Best-F1 re-pick within the rule budget |
| `../../common/fuzzy.py` | MFs (firmware-faithful), rule encoding, vectorised Sugeno AC |
| `../../common/real_data.py` | Loader + labelling + splits for `data/processed` |
| `../../common/candidates.py` | WM + enumeration candidate pool, certainty-grade consequents, pruning |
| `../../common/optimize.py` | NSGA-II (pymoo), F1/FPR/size objectives |
| `../../common/report.py` | Pareto table, rule listing, C export |

Cite: Wang & Mendel (1992) for rule generation from data; Ishibuchi, Murata &
Türkşen (1997) / Ishibuchi & Yamamoto (2004) for GA-based fuzzy rule selection with
accuracy–complexity objectives; Deb et al. (2002) for NSGA-II.
