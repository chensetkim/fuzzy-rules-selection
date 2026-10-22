# T-HFIS — hierarchical offline rule selection for FERMAD

Same methodology as CARS (`methods/cars/README.md`), applied jointly to a two-layer
hierarchy instead of one flat 7-input engine:

```
 v1,v3,v4 ─► RA  (rank-trajectory anomaly)  ─┐
 v2,v5    ─► SI  (signal instability)       ─┼─► TOP ─► AC
 v6,v7    ─► CX  (corroboration / context)  ─┘
```

Run everything with `./run_thfis.sh` from the repo root (settings in `config.sh`,
shared with CARS).

## How it selects

- **Per-unit candidate pools** (`hfs_pipeline.build_all_pools`), purely data-driven:
  full enumeration of each unit's antecedents, Ishibuchi certainty-grade consequents,
  pruned by min support (`THFIS_MIN_SUPPORT`, default 0.01) and confidence margin.
  The TOP pool is fitted against RA/SI/CX signals from the generated layer-1 pools
  (all their rules on). No hand-crafted rules are used anywhere.
- **Joint NSGA-II** over the concatenated [RA|SI|CX|TOP] masks. Every fitness
  evaluation runs the real two-layer inference. Objectives (min): 1−F1, FPR,
  total rules / max_rules, with min_rules ≤ total ≤ max_rules. Random initial
  population. With ARITH=int (default) every unit, including the uint8 truncation of
  the RA/SI/CX outputs fed to TOP, uses the mote's integer arithmetic.
- **C export:** `selected_rules.c` / `selected_rules_best_f1.c` are complete, compilable
  `fuzzrid-fuzzy-hfs.c` files for the selected hierarchy (MFs with the run's breakpoints,
  the integer Sugeno average, and the two functions declared in `c/fuzzrid-fuzzy-hfs.h`).
  They are bit-exact with the Python model under `ARITH=int`. Copy one over
  `apps/2h-fuzzrid/fuzzrid-fuzzy-hfs.c` unchanged; there is nothing to merge by hand.

## Files

| File | Purpose |
|---|---|
| `run_hfs_real_selection.py` | Primary + round-holdout selection |
| `run_hfs_loso.py` | Leave-one-scenario-out selection (S1..S6) |
| `finalize_hfs_selection.py` | Best-F1 re-pick within the rule budget |
| `hfs_pipeline.py` | Unit pools, joint NSGA-II problem, inference, reporting, C export |
| `hierarchy.py` | Hierarchy layout: which inputs feed RA / SI / CX / TOP |
| `c/fuzzrid-fuzzy-hfs.h` | Header for the generated `fuzzrid-fuzzy-hfs.c` |

Shared modules (`fuzzy.py`, `real_data.py`, `candidates.py`, `optimize.py`,
`report.py`) are in `../../common/`.
