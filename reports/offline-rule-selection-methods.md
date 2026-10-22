# Fuzzy Rule Selection for FERMAD: CARS and T-HFIS

This report explains how the two data-driven fuzzy rule-selection methods in this
repository work, based on the code. The two methods are:

- **CARS**: flat rule selection over a single 7-input Sugeno engine ([`methods/cars/`](../methods/cars/)).
- **T-HFIS**: Taxonomy-driven Hierarchical Fuzzy Inference System. It runs the same
  selection jointly over a two-layer, four-unit hierarchy
  ([`methods/thfis/`](../methods/thfis/)).

**CARS is the method adopted in this research.** T-HFIS was built and evaluated as an
alternative architecture. It is documented here (§4) because the comparison in §5
is part of the reason for choosing CARS.

> Naming: the IDS was renamed from 2H-FuzzRID to EF-RMAD, and then to **FERMAD**. Code identifiers
> (`fuzzrid_fuzzy_infer_ac`, `FUZZRID_TAU_Q_PCT`, …) still use the old name.

> **Status (2026-10-22).** This report describes the current code. Since 2026-10-22 both
> methods are purely data-driven: no hand-crafted rules exist anywhere in the code (not in
> any pool, initial population or baseline). The rule budget is 12–35, High is 0 at 50 → 1
> at 80, and rules are scored with the mote's integer arithmetic. Results (§3.7, §4.4) are
> pending new `./run_cars.sh` / `./run_thfis.sh` runs.

---

## 1. The problem both methods solve

The FERMAD detector computes seven evidence features $v_1 \dots v_7$ for every observed
neighbour, each on a $[0,100]$ scale. A zero-order Takagi–Sugeno fuzzy engine turns them
into an **Attack Confidence** $AC \in [0,100]$, and a node is flagged when
$AC \ge \tau = 65$ (`FUZZRID_TAU_Q_PCT`).

| Feature | Meaning (from [`hierarchy.py`](../methods/thfis/hierarchy.py)) | Role |
|---|---|---|
| $v_1$ | Rank monotonicity violation | inculpatory |
| $v_2$ | Trickle resets | inculpatory |
| $v_3$ | CUSUM rank drift / spike | inculpatory |
| $v_4$ | Rank jump vs. link cost | inculpatory |
| $v_5$ | Residual sign-flip count | inculpatory |
| $v_6$ | Mobility index | **exculpatory** (explains benign rank changes) |
| $v_7$ | Two-hop residual (forgery corroboration) | inculpatory |

The original engine used 18 rules, **R1–R18**, derived by hand from the attack taxonomy.
The review question behind both pipelines is *"why these 18 rules and not others?"*.
Both methods replace "expert choice" with a reproducible procedure:

```
generate a large pool of candidate rules from data
  → give each rule a consequent from data
  → prune rules that cannot discriminate
  → search rule subsets with a multi-objective GA (NSGA-II)
  → export the chosen subset as integer C for the Z1/MSP430 mote
```

---

## 2. Shared fuzzy inference core ([`fuzzy.py`](../common/fuzzy.py))

Both methods use the same shared modules in `common/` (`fuzzy.py`, `candidates.py`,
`optimize.py`, `report.py`, `real_data.py`). `fuzzy.py` re-implements the on-mote integer
inference in NumPy. With the default `ARITH=int` it is bit-exact with the firmware
(§2.3), so the rule base scored offline is scored with the arithmetic the mote will run.

### 2.1 Membership functions

Three linguistic terms per feature, on $[0,100]$ (`MFConfig`, [`fuzzy.py:55`](../common/fuzzy.py#L55)):

$$
\mu_L(x)=\mathrm{clip}\!\left(\tfrac{50-x}{30}\right),\quad
\mu_M(x)=\mathrm{clip}\!\left(\min\!\left(\tfrac{x-20}{30},\tfrac{80-x}{30}\right)\right),\quad
\mu_H(x)=\mathrm{clip}\!\left(\tfrac{x-50}{30}\right)
$$

- **Low (L)**: trapezoidal, $\mu_L(v) = 100$ on $[0, 20]$, decaying linearly to 0 at $v = 50$.
- **Medium (M)**: triangular, 0 at $v = 20$, peak 100 at $v = 50$, 0 at $v = 80$.
- **High (H)**: trapezoidal, 0 at $v = 50$, rising linearly to 100 at $v = 80$, saturated on $[80, 100]$.

These are the same sets as `mu_L`/`mu_M`/`mu_H` in the firmware's `fuzzrid-fuzzy.c`.
`--mf-high 60,90` (`MF_HIGH` in `config.sh`) reproduces the earlier High set.

The breakpoints stay **fixed** during rule selection. Only the rule set is optimised.
The three sets form a strong (Ruspini) partition: at every $x$ the memberships sum to 1
(L+M on $[20,50]$, M+H on $[50,80]$).

### 2.2 Rule encoding

A rule is a pair $(A_r, z_r)$:

- $A_r$ is a 7-tuple over $\{0,1,2,3\}$ = {don't-care, L, M, H}.
- $z_r \in \{0,25,50,75,100\}$ is a singleton consequent (VL, L, M, H, VH).

Example: `(0,0,0,H,0,L,0) → 75` reads "IF $v_4$ is High AND $v_6$ is Low THEN AC is High".

### 2.3 Firing strength and defuzzification

The firing strength uses the min t-norm over the **specified** terms only (`firing_matrix`, [`fuzzy.py:93`](../common/fuzzy.py#L93)):

$$w_r(x)=\min_{i:\,A_r[i]\neq 0}\mu_{A_r[i]}(x_i)$$

Don't-care positions are skipped, so a 2-term rule is not penalised for the other five
features. An all-don't-care rule fires at 0.

Defuzzification is the zero-order Sugeno weighted average (`sugeno_ac`, [`fuzzy.py:116`](../common/fuzzy.py#L116)).
Two arithmetic modes exist (`set_arithmetic`, [`fuzzy.py:29`](../common/fuzzy.py#L29); `ARITH` in `config.sh`):

- **`int` (default): the mote's arithmetic.** Inputs are integers 0–100. Each membership
  slope is computed with truncating integer division, e.g. $\mu_H(v)=\lfloor 100\,(v-50)/30\rfloor$,
  so memberships and firing strengths are integers 0–100. Then
  $$AC(x)=\left\lfloor\frac{\sum_{r\in S}w_r(x)\,z_r}{1+\sum_{r\in S}w_r(x)}\right\rfloor$$
  exactly as `fuzzrid-fuzzy.c` computes it (`num/den`, `den = 1`). This mode was checked
  against the firmware's own C functions: identical AC on 40,000 of 40,000 cases
  (200 random rule bases × 200 random inputs).
- **`float`: the continuous model.** Memberships in $[0,1]$ and
  $AC=\sum w_r z_r / (\sum w_r+\varepsilon)$ with $\varepsilon=0.01$, the $[0,1]$-scale analogue
  of `den = 1`. It differs from the mote mainly where the rules barely fire: on random
  inputs the flat engine's decision differed in 0.14 % of cases and a two-layer T-HFIS
  base's in 4.6 %, because each layer's output is also truncated on the mote.

If no rule fires, $AC=0$ ("no evidence → no attack").

---

## 3. CARS: flat rule selection (the adopted method)

### 3.1 Data and labelling ([`common/real_data.py`](../common/real_data.py))

**Corpus.** The input CSVs live under `data/processed/{mobile,static}/r{1,2,3}/{3,6,9}/*-S{1..6}-*.csv`. The dimensions are:

- environment: mobile or static;
- round: three independent simulation repetitions;
- attacker count: 3, 6 or 9;
- attack type: S1–S6.

**Attacker IDs.** These come from the attacker-count path segment: 3 → {29–31}, 6 → {26–31}, 9 → {23–31}.

**Label.**

$$y=1 \iff src\in\text{attackers} \;\wedge\; t\ge 300\,\text{s (attack launch)}$$

**Two exclusion rules** (`load_real_events`, [`real_data.py:65`](../common/real_data.py#L65)):

1. *Rows observed **by** an attacker are dropped.* An attacker does not run the IDS honestly, so its observations are not evidence the real system would use.
2. *Rows observed **of** an attacker before launch are dropped*, not labelled benign. Before launch the attacker behaves honestly. Labelling those rows either way would put label noise into an unlearnable region.

**Static de-duplication.** The static simulation is deterministic, so static r1/r2/r3 are byte-identical files. Only static r1 is loaded; otherwise every static row would be counted three times.

**Clean corpus:** 388,338 detection events (83,781 attack / 304,557 benign, 21.6 % positive).

### 3.2 Candidate pool ([`candidates.py`](../common/candidates.py))

Two generators feed one pool. They complement each other.

**Generator A: Wang–Mendel-style cell rules** (`wang_mendel_antecedents`, [`candidates.py:36`](../common/candidates.py#L36)).

- Each training sample is assigned to its strongest term per feature (argmax membership), which gives one full 7-term antecedent.
- The unique cells are ranked by occupancy and capped at 200.
- This anchors the pool in the regions of the $3^7$ grid that the data actually occupies.
- It deviates from textbook Wang–Mendel: there is no rule degree, and conflicts are resolved by the consequent step below.

**Generator B: bounded enumeration** (`enumerate_antecedents`, [`candidates.py:49`](../common/candidates.py#L49)).

- It generates every antecedent that specifies 1 to 4 features:

$$\sum_{k=1}^{4}\binom{7}{k}3^k = 21+189+945+2835 = 3990 \text{ rules}$$

- This generator is needed because Wang–Mendel rules always use all 7 features.
- Without it, short, readable rules (1–4 terms) could not be reached.
- The 4-term cap is an interpretability limit.

**Consequent assignment: Ishibuchi certainty grade** (`assign_consequents`, [`candidates.py:61`](../common/candidates.py#L61)). The training set is used for this:

$$
\mathrm{conf}(r)=\frac{\sum_{x:y=1}w_r(x)}{\sum_x w_r(x)},\qquad
\mathrm{supp}(r)=\frac{1}{n}\sum_x w_r(x),\qquad
z_r=\arg\min_{z\in\{0,25,50,75,100\}}\left|100\,\mathrm{conf}(r)-z\right|
$$

Confidence is the firing-weighted share of attack samples the rule covers. Support is the rule's mean firing strength.

**Pruning** ([`candidates.py:95`](../common/candidates.py#L95)). A candidate is kept only if both conditions hold:

$$\mathrm{supp}(r)\ge 0.005 \quad\text{and}\quad |\mathrm{conf}(r)-0.5|\ge 0.15$$

- The support floor removes rules that almost never fire.
- The confidence margin removes rules that fire equally on attacks and benign traffic. Such rules carry no information and only dilute the weighted average.
- Side effect: a kept rule has conf ≤ 0.35 or ≥ 0.65, so **no selected rule can get $z=50$**.

**No hand-crafted rules.** The pool is purely data-driven, and the code contains no
hand-crafted rule base at all (no injection, no baseline, no overlap report). The pool
size is printed in each run's `select.log`.

### 3.3 Multi-objective subset selection ([`optimize.py`](../common/optimize.py))

**Encoding.** A chromosome is a binary vector of length $|P|$, several hundred candidates. Bit $j$ = 1 means "rule $j$ is in the base". The space has $2^{|P|}$ subsets, so exhaustive search is impossible and a metaheuristic is justified.

**Objectives, all minimised** (`RuleSelectionProblem._evaluate`, [`optimize.py:56`](../common/optimize.py#L56)):

| | Objective | Reason |
|---|---|---|
| $f_1$ | $1-F_1$ (train) | detection quality under class imbalance (plain accuracy would be dominated by the benign majority) |
| $f_2$ | FPR (train) | operational cost. It is a separate axis because, under the base-rate fallacy, even small FPRs dominate the alert stream at deployment scale |
| $f_3$ | $\lvert S\rvert/\text{max\_rules}$ | Z1 RAM/flash budget and interpretability |

**Constraints:** $12 \le |S| \le 35$ (`MIN_RULES`, `MAX_RULES` in `config.sh`). An empty chromosome gets $F=[1,1,0]$ and is marked infeasible.

**Algorithm:** NSGA-II (pymoo). The settings for the real-data run are:

| Setting | Value | Why |
|---|---|---|
| Population × generations | 150 × 250 | 37,500 evaluations |
| Crossover | Uniform, $p=0.9$ | rules are an unordered set, so bit position carries no locality |
| Mutation | Bit-flip, $1/n_{var}$ per bit | about one flip per individual |
| Duplicates | eliminated | keeps diversity on a plateau-heavy landscape |
| Fitness data | 40,000-row stratified subsample of the train split | makes the firing matrix tractable; all reported metrics use the **full** test split |

**Random initial population** (`random_population`, [`optimize.py:76`](../common/optimize.py#L76)):
every individual is a sparse random subset (each rule on with probability 0.02). No
rule base is seeded.

### 3.4 Picking one base from the Pareto front

NSGA-II returns a front of non-dominated bases. Two pickers exist:

- **Knee pick** (`knee_solution`, [`optimize.py:104`](../common/optimize.py#L104)).
  - Each objective is min-max normalised, then weighted $0.6/0.3/0.1$ (F1 / FPR / size) and summed; the minimum wins.
  - It uses **training objectives only**.
  - Despite the name, this is a preference-weighted scalarisation, not a geometric knee.
  - Output: `selected_rules.{txt,c}`.
- **Best-F1 pick** (`pick_best`, [`finalize_selection.py:38`](../methods/cars/finalize_selection.py#L38)).
  - It takes the highest `f1_test` inside the rule budget, with ties within 0.002 going to fewer rules.
  - Output: `selected_rules_best_f1.{txt,c}`.

> ⚠️ The best-F1 pick chooses the base **using the test split**. Its test score is therefore
> slightly optimistic, because selection and evaluation share data. The knee pick does
> not have this problem. If the best-F1 base is the one deployed, either report its
> numbers as validation-selected, or re-pick it on a separate validation split.

### 3.5 Outputs and C export ([`report.py`](../common/report.py))

| File | Content |
|---|---|
| `pareto_front.csv` | every non-dominated base: train/test F1, FPR, recall, precision, size |
| `selected_rules.txt` | chosen base, human-readable, with per-rule support and confidence |
| `selected_rules.c` | same base as the rule block of `fuzzrid_fuzzy_infer_ac()` |

`export_c` ([`report.py:53`](../common/report.py#L53)) emits one line per rule, with nested
`min2()` for multi-term antecedents. It then emits the same $\varepsilon=1$ integer weighted
average as the firmware:

```c
/* G97(enum): v3 is H AND v6 is M -> 75 */
w[2] = min2(mu_H(v3), mu_M(v6));  zc[2] = 75;
...
uint32_t num = 0, den = 1; /* eps = 1 */
for(r = 1; r <= n; r++) { num += (uint32_t)w[r] * zc[r]; den += w[r]; }
return (uint8_t)(num / den);
```

The base deploys **unchanged**. There is no manual transcription step between the rules
that were evaluated and the rules that run on the mote, and with `ARITH=int` the offline
scores are the mote's own AC values.

### 3.6 Validation design: three splits

| Split | Train | Test | Question |
|---|---|---|---|
| **Primary** ([`real_data.py:153`](../common/real_data.py#L153)) | 70 % of each scenario, shuffled | remaining 30 % | held-out accuracy |
| **Round-holdout** ([`real_data.py:170`](../common/real_data.py#L170)) | mobile r1+r2, static r1 | mobile **r3** | does it transfer to a fresh mobility realisation? |
| **LOSO** ([`real_data.py:179`](../common/real_data.py#L179)) | 5 of 6 attack types | the 6th | does it transfer to an **unseen attack type**? |

Each split is a complete, independent re-run of pool building and NSGA-II. The primary
split shuffles rows *within* each run, so autocorrelated neighbouring events can fall on
both sides and inflate the score. The other two splits exist to measure how much.

### 3.7 CARS results

**Pending.** Produce them with `./run_cars.sh`, preferably `SEEDS="1 2 3 4 5"`, and take
the tables from the run's `SUMMARY.md` (rules, F1, FPR, recall and precision for the
primary and round-holdout knee and best-F1 bases, each LOSO fold, and the LOSO mean).
The results quoted here before 2026-10-22 came from the old procedure (expert rules
injected, 12–29 rules, High 60–90, float scoring) and no longer describe the method; they
are kept, marked as legacy, in `reports/RULE_SELECTION_RESULTS.md` and
`outputs/legacy_2026-09/`.

---

## 4. T-HFIS: hierarchical rule selection (evaluated, not adopted)

### 4.1 Architecture ([`hierarchy.py`](../methods/thfis/hierarchy.py))

T-HFIS decomposes the flat 7-input engine into two layers. The grouping follows the
attack taxonomy:

```
Layer 1                                     Layer 2
RA  = f_RA(v1, v3, v4)  rank-trajectory anomaly ─┐
SI  = f_SI(v2, v5)      signal instability      ─┼─► AC = f_TOP(RA, SI, CX)
CX  = f_CX(v6, v7)      corroboration/context   ─┘
                        (0 = mobility-excused, 50 = neutral, 100 = forged)
```

All four units are ordinary zero-order Sugeno engines, using the §2 machinery unchanged.
The intermediate outputs RA, SI and CX are on $[0,100]$ and are re-fuzzified with the
same L/M/H sets before entering TOP.

**Complexity bound.** The complete grids total $3^3+3^2+3^2+3^3=72$ rules. The flat grid has $3^7=2187$.

**Only the layout is fixed.** `hierarchy.py` defines which inputs feed which unit; every rule in every unit is selected from data.

### 4.2 Per-unit candidate pools ([`hfs_pipeline.py`](../methods/thfis/hfs_pipeline.py))

`build_unit_pool` ([`hfs_pipeline.py:72`](../methods/thfis/hfs_pipeline.py#L72)) builds one pool per unit:

- **Full enumeration.** Every unit has at most 3 inputs, so every antecedent is enumerated: 63 for RA and TOP ($9+27+27$), 15 for SI and CX ($6+9$). There is no Wang–Mendel step; with a grid this small, enumeration already covers every cell.
- **Consequents.** Same Ishibuchi certainty grade as CARS.
- **Pruning.** A support floor of 0.01 (vs 0.005 in CARS) and the same 0.15 confidence margin.
- **No hand-crafted rules**, as in CARS.
- **TOP pool reference signal.** The TOP pool has a special problem: its inputs (RA, SI, CX) depend on which layer-1 rules are selected. So TOP consequents are assigned against a *reference* signal: the outputs of the generated layer-1 pools with all their rules on (`build_all_pools`, [`hfs_pipeline.py:97`](../methods/thfis/hfs_pipeline.py#L97)).

Pool sizes per unit are printed in each run's `select.log`.

### 4.3 Joint NSGA-II ([`hfs_pipeline.py:163`](../methods/thfis/hfs_pipeline.py#L163))

- **Chromosome.** The concatenation `[RA | SI | CX | TOP]` of the four unit masks.
- **Fitness.** Every evaluation runs the **real two-layer inference**. RA, SI and CX are recomputed from whichever layer-1 rules that individual switched on, re-fuzzified, and then fed through that individual's TOP rules.
- **Objectives, constraints and operators.** Identical to CARS: $(1-F_1,\ \mathrm{FPR},\ |S|/35)$ with $12\le|S|\le35$, where the count covers the whole hierarchy.
- **Initial population.** Random, 5 % density.
- **Arithmetic.** With `ARITH=int` each unit uses the mote's integer arithmetic, including the truncation of RA, SI and CX to integers before they enter TOP.


**Export.** `export_c_hfs` writes `selected_rules.c` as a complete, compilable
`fuzzrid-fuzzy-hfs.c`: the membership functions with the run's breakpoints, the integer
Sugeno average, the four unit functions and the two entry points declared in
[`methods/thfis/c/fuzzrid-fuzzy-hfs.h`](../methods/thfis/c/fuzzrid-fuzzy-hfs.h). It is
bit-exact with the Python model under `ARITH=int` (checked on 10 generated bases × 20,000
random inputs) and is copied into the firmware unchanged, enabled by `-DWITH_THFIS=1`
([`reports/thfis-implement.md`](thfis-implement.md)).

### 4.4 T-HFIS results

**Pending**, as for CARS (§3.7): run `./run_thfis.sh` with the same `config.sh` and take the
tables from its `SUMMARY.md`.

---

## 5. CARS vs T-HFIS: design comparison

| | CARS (flat) | T-HFIS (hierarchical) |
|---|---|---|
| Inference | one 7-input Sugeno unit | four chained Sugeno units |
| Candidate pool | enumeration of ≤4-term antecedents + Wang–Mendel cells | full enumeration per unit |
| Firmware cost | 1 integer divide, 1 rule loop | 4 divides, 4 loops, re-fuzzification of 3 intermediates |
| Consequent fitting | exact: each rule's certainty grade uses the real inputs | approximate for TOP: fitted against a reference layer 1 (all generated layer-1 rules on) that differs from the selected one |
| Interpretability | each rule reads directly in terms of $v_1..v_7$ | TOP rules read in terms of abstract RA/SI/CX scores |
| Deployment | `selected_rules.c` = rule block for `fuzzrid_fuzzy_infer_ac()` | `selected_rules.c` = complete `fuzzrid-fuzzy-hfs.c` |

**Design reasons for preferring CARS.** The accuracy comparison waits for the new runs
(§3.7, §4.4); independently of it:

1. **Simpler and cheaper on the mote.** CARS has one weighted average and a single divide. It needs no intermediate re-fuzzification and has no layer-1/TOP coupling to keep consistent.
2. **Cleaner method.** Every CARS consequent is fitted on the inputs the rule actually sees. The T-HFIS TOP consequents are fitted on a reference signal, which is an approximation; a selected TOP rule can end up with near-zero support on the selected layer 1.
3. **Direct readability.** A CARS rule such as "IF $v_2$ is H AND $v_3$ is H AND $v_5$ is L AND $v_6$ is L THEN VH" can be checked against protocol behaviour without decoding intermediate scores.

---

## 6. Limitations to state with the CARS results

1. **Unseen attack types.** LOSO measures transfer to an attack type never seen during selection; in earlier runs it was the weakest split (some folds far below the primary F1). Report LOSO mean ± std alongside the primary number, not the primary number alone.
2. **Best-F1 pick uses the test split** (§3.4). The knee numbers are the clean held-out numbers.
3. **Primary split autocorrelation.** Rows are shuffled within runs. The round-holdout and LOSO splits bound the effect.
4. **Seeds.** The split, initial population and GA randomness are all fixed by one seed. Report results over several seeds (`SEEDS="1 2 3 4 5" ./run_cars.sh` gives mean ± std in `SUMMARY.md`).
5. **Fixed membership functions.** Rules are selected under High = [50, 80], the firmware's setting; a base selected under one MF setting does not transfer to another. Do not tune MFs and rules on the same split.
6. **No $z=50$ for generated rules.** This is a side effect of the 0.15 confidence margin (§3.2).
7. **No comparison with a hand-crafted base.** The method and the code score only data-selected bases; there is no expert baseline.
8. **Simulation labels.** Ground truth is attacker mote IDs in Cooja, so the results inherit the simulation's topology and mobility scope.

---

## 7. Reproducing

```bash
./run_cars.sh                    # CARS: select (primary + round-holdout) → LOSO → best-F1 → SUMMARY.md
./run_thfis.sh                   # T-HFIS: same steps
SEEDS="1 2 3 4 5" ./run_cars.sh  # multi-seed, mean ± std in SUMMARY.md
QUICK=1 ./run_cars.sh            # smoke test
```

Both read every setting from `config.sh` (rule budget, MFs, threshold, arithmetic, split,
seeds, NSGA-II sizes), so the two methods always run with the same values. Each run writes
`outputs/<method>/run_<date>_<time>/` with `config.txt` (all settings + git commit),
`SUMMARY.md` and `seed_<s>/{primary,round_holdout,loso/S1..S6}/`.

## References

- L.-X. Wang, J. M. Mendel, "Generating fuzzy rules by learning from examples," *IEEE TSMC* 22(6), 1992.
- H. Ishibuchi, T. Murata, I. B. Türkşen, "Single-objective and two-objective genetic algorithms for selecting linguistic rules for pattern classification problems," *Fuzzy Sets Syst.* 89(2), 1997.
- H. Ishibuchi, T. Yamamoto, "Fuzzy rule selection by multi-objective genetic local search algorithms and rule evaluation measures in data mining," *Fuzzy Sets Syst.* 141(1), 2004.
- K. Deb et al., "A fast and elitist multiobjective genetic algorithm: NSGA-II," *IEEE TEVC* 6(2), 2002.
- J. Blank, K. Deb, "pymoo: Multi-objective optimization in Python," *IEEE Access* 8, 2020.
- T. Takagi, M. Sugeno, "Fuzzy identification of systems and its applications to modeling and control," *IEEE TSMC* 15(1), 1985.
- S. Axelsson, "The base-rate fallacy and the difficulty of intrusion detection," *ACM TISSEC* 3(3), 2000.
- D. Arp et al., "Dos and don'ts of machine learning in computer security," *USENIX Security*, 2022.
- M. J. Gacto, R. Alcalá, F. Herrera, "Interpretability of linguistic fuzzy rule-based systems," *Inf. Sci.* 181(20), 2011.

Full technical detail for CARS: [`reports/rules-selection-for-FERMAD.md`](rules-selection-for-FERMAD.md).
