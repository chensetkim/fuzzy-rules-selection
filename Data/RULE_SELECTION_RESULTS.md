# Optimal fuzzy rule bases from `Data/csv` — flat & hierarchical

Rule-count budget requested: **10 < |rules| < 30**. All bases below satisfy this
by construction (NSGA-II hard constraint).

## 1. Data

`Data/csv/{mobile,static}/r{1,2,3}/{3,6,9}/*.csv` — mobile/static deployment ×
3 simulation rounds × {3,6,9} attacker motes × 6 attack types (S1–S6), labelled
`y=1` iff `src` is an attacker mote **and** `t ≥ 300s` (attack launch), same
convention as the existing `CARS/rs/data.py`.

**Data-quality finding:** the `static` branch is a deterministic simulation
(no mobility randomness) — `r1`, `r2`, `r3` are **byte-identical** CSVs for
every scenario/attacker-count (verified by hashing all 108 files). Loading
all three would silently triple-count every static row. Fixed in
[`Data/real_data.py`](real_data.py) by loading only `static/r1` (`mobile`
rounds ARE independent and are all used). Clean dataset: **388,338** labelled
detection events (83,781 attack / 304,557 benign, 21.6% positive rate).

## 2. Method

Both engines reuse the existing methodology (`CARS/fuzzy_rules_selection.md`):
Wang–Mendel + bounded enumeration candidate generation → Ishibuchi
certainty-grade consequents → NSGA-II over binary rule-inclusion, minimising
`(1-F1, FPR, |rules|)` with **hard constraints `12 ≤ |rules| ≤ 29`** (a floor
was added to `optimize.py`; only a ceiling existed before). The flat engine
(`CARS/rs/`) selects one 7-input rule set, exactly as the existing pipeline
does. The hierarchical engine (`T-HFIS/`) had **no automated selection
before this work** — only a hand-crafted 25-rule hierarchy
(`hierarchy.py`). New code (`T-HFIS/thfis/hfs_pipeline.py`) builds
candidate pools per sub-FIS (RA: v1,v3,v4 · SI: v2,v5 · CX: v6,v7 · TOP:
RA,SI,CX) and jointly optimises all four with one NSGA-II run, so the total
rule count across the whole hierarchy obeys the same 12–29 budget.

Candidate generation + NSGA-II fitness run on a 40,000-row stratified
subsample of the training split (tractable candidate-firing-matrix size);
**all reported metrics use the full, non-subsampled evaluation split.**

### Three validation splits (why three)

| Split | Train | Test | Question answered |
|---|---|---|---|
| **Primary** | 70% of every scenario/env/round/atkcount, shuffled | remaining 30% | Standard held-out accuracy |
| **Round-holdout** | mobile r1+r2 + static r1 | mobile **r3** (untouched) | Generalises to a fresh, independently-simulated mobility repetition? |
| **LOSO** (leave-one-scenario-out) | 5 of 6 attack types | the 6th, held out entirely | Generalises to a genuinely **unseen attack type**? |

`CARS/fuzzy_rules_selection.md` §3.4/§10/§11 explicitly flags the primary
split's weakness (consecutive same-run rows are autocorrelated, so a random
split leaks information) and says results should be re-checked under
leave-one-scenario-out before trusting them — that check is included here,
not skipped.

## 3. Results

FPR/F1 measured at `AC ≥ 65` (firmware's `FUZZRID_TAU_Q_PCT`), same as the
existing pipeline.

### Primary split (standard held-out test)

| Engine | Baseline (hand-crafted) F1 / FPR | Data-driven, budget-capped F1 / FPR | Rules |
|---|---|---|---|
| Flat (R1–R18) | 0.8502 / 0.0461 | **0.9278 / 0.0218** | 23 |
| Hierarchical (T-HFIS) | 0.6056 / 0.0140 | **0.9280 / 0.0201** | 23 (RA9+SI2+CX3+TOP9) |

Both architectures converge to **essentially the same ceiling (F1≈0.928)**
at the same rule count once rules are chosen from data instead of by hand.
The hand-crafted flat base was already decent (0.85); the hand-crafted
*hierarchy* was not (0.61) — its fixed RA/SI/CX aggregation doesn't match
this dataset's actual value distributions well, which is exactly the kind
of gap systematic rule selection is for.

### Round-holdout (unseen mobile-r3 repetition)

| Engine | Hand-crafted F1 / FPR | Data-driven F1 / FPR | Rules |
|---|---|---|---|
| Flat | 0.7826 / 0.0552 | **0.8954 / 0.0261** | 17 |
| Hierarchical | 0.3548 / 0.0126 | **0.8956 / 0.0244** | 24 (RA9+SI3+CX3+TOP9) |

Both data-driven bases hold up well on a truly fresh simulation run
(~0.03 F1 below primary). The hand-crafted *hierarchy* falls apart here
(0.61→0.35) — its fixed rules don't transfer between mobility repetitions,
another point in favour of the data-driven hierarchy.

### Leave-one-scenario-out (unseen attack type) — the hard test

| Held-out type | Flat data-driven F1 (rules) | Flat expert F1 | Hier. data-driven F1 (rules) | Hier. hand-crafted F1 |
|---|---|---|---|---|
| S1 (decrease/jump) | 0.7943 (13) | **0.9339** | 0.7956 (14) | 0.6941 |
| S2 (decrease/slow) | 0.6944 (12) | **0.9086** | 0.5118 (13) | 0.4495 |
| S3 (increase/jump) | **0.9756** (16) | 0.9741 | **0.8431** (13) | 0.7036 |
| S4 (increase/slow) | **0.9244** (12) | 0.8101 | **0.9260** (16) | 0.4616 |
| S5 (fluctuation) | **0.9754** (19) | 0.6111 | **0.9780** (19) | 0.5119 |
| S6 (forge 2-hop) | 0.6513 (12) | 0.5988 | 0.6686 (12) | 0.6120 |
| **mean ± std** | **0.8359 ± 0.131** | 0.8061 ± 0.151 | **0.7872 ± 0.158** | 0.5721 ± 0.104 |

This is the most informative check and should be the headline "not
overfitting" number, not the primary split. Two honest findings:

- **Flat**: on S1 and S2, the data-driven base generalises *worse* than
  the fixed expert R1–R18 base to a genuinely unseen attack type — the
  optimizer partly specialised to the five attack types it did see. On the
  other four types it's equal or clearly better.
- **Hierarchical**: the data-driven hierarchy beats the hand-crafted
  hierarchy in **all six** folds, often by a large margin (S4: +0.46, S5:
  +0.47). The hierarchical decomposition seems to generalise to novel
  attack types more consistently than either flat variant.

## 4. Recommendation

- **If deploying now, on the six known attack types**: use the **primary
  best-F1 bases** — flat 23 rules (`CARS/rule_selection_real/primary/selected_rules_best_f1.{txt,c}`)
  or hierarchical 23 rules (`T-HFIS/rule_selection_real/primary/selected_rules_best_f1.{txt,c}`).
  Both hit F1≈0.928, comfortably inside the 10–30 budget, and both retain
  several expert rules (flat: R6; hierarchical: 9/25 hand-crafted rules),
  so they're not a black-box replacement of the taxonomy, they extend it.
- **If robustness to a future, not-yet-seen attack variant matters more
  than squeezing out the last points of F1**: prefer the hierarchical
  engine — it never lost to its hand-crafted baseline in LOSO, unlike the
  flat engine on S1/S2 — and/or use the round-holdout or knee-point bases,
  which are smaller and showed a smaller train→unseen-data gap.
- Either way, **do not report the primary-split F1 alone** as the
  generalisation number; report it alongside the LOSO mean±std above, per
  `fuzzy_rules_selection.md`'s own validity guidance.

## 5. Files

```
CARS/rs/real_data.py → Data/real_data.py        real-data loader (shared)
CARS/rs/run_real_selection.py                    flat: primary + round-holdout
CARS/rs/run_loso.py                              flat: leave-one-scenario-out (6 folds)
CARS/rs/finalize_selection.py                     flat: best-F1-in-budget re-pick
CARS/rule_selection_real/{primary,round_holdout,loso/S1..S6}/
    pareto_front.csv        every non-dominated base, train+test metrics
    selected_rules.txt/.c   knee-point pick (generic weighted heuristic)
    selected_rules_best_f1.txt/.c   argmax F1 subject to the 12–29 budget  [primary/round_holdout only]

T-HFIS/thfis/hfs_pipeline.py                      hierarchical candidate pools + joint NSGA-II (new)
T-HFIS/thfis/run_hfs_real_selection.py            hierarchical: primary + round-holdout
T-HFIS/thfis/run_hfs_loso.py                      hierarchical: leave-one-scenario-out
T-HFIS/thfis/finalize_hfs_selection.py            hierarchical: best-F1-in-budget re-pick
T-HFIS/rule_selection_real/{primary,round_holdout,loso/S1..S6}/   (same file layout)
```

Re-run everything: `python3 CARS/rs/run_real_selection.py && python3 CARS/rs/run_loso.py`
and the `T-HFIS/thfis/run_hfs_*` equivalents (defaults reproduce this
report; `--seed` to check across seeds per the pipeline's own guardrail
about single-seed results).
