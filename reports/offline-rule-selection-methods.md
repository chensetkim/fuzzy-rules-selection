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

> **Status (2026-10-22).** §1–§4 and §6–§7 describe the current code. The method changed on
> 2026-10-22: no expert rules are injected into any pool or initial population, the rule
> budget is 12–35, High is 0 at 50 → 1 at 80, and rules are scored with the mote's integer
> arithmetic. **The numbers in §3.7, §4.4 and §5 are legacy results** made with the old
> settings (expert-seeded, 12–29 rules, High 60–90, float scoring; files in
> `outputs/legacy_2026-09/`). They will be replaced after new `./run_cars.sh` /
> `./run_thfis.sh` runs.

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

Example: R3 = `(0,0,0,H,0,L,0) → 75` reads "IF $v_4$ is High AND $v_6$ is Low THEN AC is High".

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

**Generator A: Wang–Mendel-style cell rules** (`wang_mendel_antecedents`, [`candidates.py:38`](../common/candidates.py#L38)).

- Each training sample is assigned to its strongest term per feature (argmax membership), which gives one full 7-term antecedent.
- The unique cells are ranked by occupancy and capped at 200.
- This anchors the pool in the regions of the $3^7$ grid that the data actually occupies.
- It deviates from textbook Wang–Mendel: there is no rule degree, and conflicts are resolved by the consequent step below.

**Generator B: bounded enumeration** (`enumerate_antecedents`, [`candidates.py:51`](../common/candidates.py#L51)).

- It generates every antecedent that specifies 1 to 4 features:

$$\sum_{k=1}^{4}\binom{7}{k}3^k = 21+189+945+2835 = 3990 \text{ rules}$$

- This generator is needed because Wang–Mendel rules always use all 7 features, while R1–R18 use 1–5.
- Without it, short, readable rules like those of R1–R18 could not be reached.
- The 4-term cap is an interpretability limit.

**Consequent assignment: Ishibuchi certainty grade** (`assign_consequents`, [`candidates.py:63`](../common/candidates.py#L63)). The training set is used for this:

$$
\mathrm{conf}(r)=\frac{\sum_{x:y=1}w_r(x)}{\sum_x w_r(x)},\qquad
\mathrm{supp}(r)=\frac{1}{n}\sum_x w_r(x),\qquad
z_r=\arg\min_{z\in\{0,25,50,75,100\}}\left|100\,\mathrm{conf}(r)-z\right|
$$

Confidence is the firing-weighted share of attack samples the rule covers. Support is the rule's mean firing strength.

**Pruning** ([`candidates.py:97`](../common/candidates.py#L97)). A candidate is kept only if both conditions hold:

$$\mathrm{supp}(r)\ge 0.005 \quad\text{and}\quad |\mathrm{conf}(r)-0.5|\ge 0.15$$

- The support floor removes rules that almost never fire.
- The confidence margin removes rules that fire equally on attacks and benign traffic. Such rules carry no information and only dilute the weighted average.
- Side effect: a kept rule has conf ≤ 0.35 or ≥ 0.65, so **no selected rule can get $z=50$**.

**No hand-crafted rules.** The pool is purely data-driven: R1–R18 are never added to it,
and the code no longer contains R1–R18 at all (no built-in baseline, no overlap report).
The pool size is printed in each run's `select.log` (legacy run: 701 candidates, of
which 18 were injected expert rules).

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
expert base is seeded, so the search is not anchored on R1–R18.

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

`export_c` ([`report.py:70`](../common/report.py#L70)) emits one line per rule, with nested
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

### 3.7 CARS results (legacy — old settings)

> ⚠️ **Legacy numbers.** Produced before 2026-10-22 with R1–R18 injected into the pool and
> seeded into the initial population, a 12–29 rule budget, High 60–90 and float scoring
> (`outputs/legacy_2026-09/cars/`). They do not describe the current method. Re-run
> `./run_cars.sh` (ideally `SEEDS="1 2 3 4 5"`) and replace this section with its `SUMMARY.md`.

**Primary and round-holdout**, at $\tau=65$:

| Base | Rules | F1 | FPR | Recall | Precision | Expert rules kept |
|---|---|---|---|---|---|---|
| R1–R18 (hand-crafted), primary | 18 | 0.8502 | 0.0461 | – | – | 18/18 |
| CARS knee, primary | 15 | 0.9153 | 0.0061 | 0.8628 | 0.9747 | 1/18 (R6) |
| CARS best-F1, primary | 23 | 0.9278 | 0.0218 | 0.9341 | 0.9216 | 1/18 (R6) |
| R1–R18, round-holdout | 18 | 0.7826 | 0.0552 | – | – | – |
| CARS knee, round-holdout | 15 | 0.8317 | 0.0038 | 0.7239 | 0.9774 | 0/18 |
| CARS best-F1, round-holdout | 17 | 0.8954 | 0.0261 | 0.9042 | 0.8869 | 0/18 |

**Leave-one-scenario-out** (knee bases, pop 80 × 120 gens):

| Held-out | Rules | CARS F1 | R1–R18 F1 | FPR | Recall | Precision |
|---|---|---|---|---|---|---|
| S1 decrease/jump | 13 | 0.7943 | **0.9339** | 0.0072 | 0.6713 | 0.9725 |
| S2 decrease/slow | 12 | 0.6944 | **0.9086** | 0.0054 | 0.5416 | 0.9674 |
| S3 increase/jump | 16 | **0.9756** | 0.9741 | 0.0037 | 0.9623 | 0.9893 |
| S4 increase/slow | 12 | **0.9244** | 0.8101 | 0.0072 | 0.8948 | 0.9559 |
| S5 fluctuation | 19 | **0.9754** | 0.6111 | 0.0082 | 0.9902 | 0.9610 |
| S6 forge 2-hop | 12 | **0.6513** | 0.5988 | 0.0066 | 0.4967 | 0.9460 |
| **mean ± std** | | **0.836 ± 0.131** | 0.806 ± 0.151 | | | |

**How to read these (legacy) results:**

- **CARS beats the hand-crafted base on every split in aggregate.** It improves F1 (+0.065 knee, +0.078 best-F1 on primary) *and* cuts FPR by roughly 2–8×.
- **The FPR drop is the biggest operational gain.** For example, the knee base has 0.0061 FPR vs 0.0461.
- **Known attack types transfer to a new round well.** The round-holdout gap is about 0.03 F1 (best-F1) or 0.08 (knee), so the primary number is not purely split leakage.
- **Unseen attack types are the weak spot.**
  - S2 and S6 fall to 0.69 and 0.65, and on S1/S2 the fixed R1–R18 base generalises better.
  - Precision stays 0.95–0.99 in every fold. The failure mode is always *missed* detections, never false alarms.
- **Expert overlap is at chance level.** Only R6 ("$v_3$ High AND $v_6$ Low → H") survives. With 18 experts in a 701-rule pool, keeping 1 is what random selection would give ($P(\ge1)\approx0.33$). So CARS *replaces* the taxonomy base rather than confirming it. Any interpretability claim has to rest on reading the selected rules themselves.

**What the selected rules say** (primary best-F1):

- $v_2$ (Trickle resets) at Medium or High is the dominant attack indicator. It appears in 14 of 23 rules, mostly with $z=100$.
- $v_3$ High combined with $v_6$ Medium/Low gives $z=75$.
- One broad rule, G12 ("$v_5$ Low AND $v_6$ Medium → L", support 0.47), carries the benign majority down.

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

**Hand-crafted base.** It has 25 rules (6 RA + 5 SI + 5 CX + 9 TOP). Each rule cites the flat rule it descends from.

**Behaviour change vs. the flat base.** Rule T3 discounts a High rank anomaly to $AC=50$ when context is exculpatory (CX Low). In flat R1, a High rank anomaly always gives VH.

### 4.2 Per-unit candidate pools ([`hfs_pipeline.py`](../methods/thfis/hfs_pipeline.py))

`build_unit_pool` ([`hfs_pipeline.py:88`](../methods/thfis/hfs_pipeline.py#L88)) builds one pool per unit:

- **Full enumeration.** Every unit has at most 3 inputs, so every antecedent is enumerated: 63 for RA and TOP ($9+27+27$), 15 for SI and CX ($6+9$). There is no Wang–Mendel step; with a grid this small, enumeration already covers every cell.
- **Consequents.** Same Ishibuchi certainty grade as CARS.
- **Pruning.** A support floor of 0.01 (vs 0.005 in CARS) and the same 0.15 confidence margin.
- **No expert injection.** As in CARS, no hand-crafted RA/SI/CX/TOP rule is added to any pool; `expert_mask` only flags generated rules that share a hand-crafted antecedent (overlap reporting).
- **TOP pool reference signal.** The TOP pool has a special problem: its inputs (RA, SI, CX) depend on which layer-1 rules are selected. So TOP consequents are assigned against a *reference* signal: the outputs of the generated layer-1 pools with all their rules on (`build_all_pools`, [`hfs_pipeline.py:120`](../methods/thfis/hfs_pipeline.py#L120)). No hand-crafted rule is involved. (Until 2026-10-22 the reference was the hand-crafted layer 1.)

Pool sizes per unit are printed in each run's `select.log` (legacy run: 78 candidates, of which 25 were injected hand-crafted rules).

### 4.3 Joint NSGA-II ([`hfs_pipeline.py:193`](../methods/thfis/hfs_pipeline.py#L193))

- **Chromosome.** The concatenation `[RA | SI | CX | TOP]` of the four unit masks.
- **Fitness.** Every evaluation runs the **real two-layer inference**. RA, SI and CX are recomputed from whichever layer-1 rules that individual switched on, re-fuzzified, and then fed through that individual's TOP rules.
- **Objectives, constraints and operators.** Identical to CARS: $(1-F_1,\ \mathrm{FPR},\ |S|/35)$ with $12\le|S|\le35$, where the count covers the whole hierarchy.
- **Initial population.** Random, 5 % density; no hand-crafted rules are seeded.
- **Arithmetic.** With `ARITH=int` each unit uses the mote's integer arithmetic, including the truncation of RA, SI and CX to integers before they enter TOP.
- **Baseline.** The hand-crafted 25-rule hierarchy is scored on the same test set for comparison only.

**Export.** `export_c_hfs` emits four chained Sugeno blocks. The deployable firmware is
[`methods/thfis/c/fuzzrid-fuzzy-hfs.c`](../methods/thfis/c/fuzzrid-fuzzy-hfs.c). It is enabled by `-DWITH_THFIS=1`
([`reports/thfis-implement.md`](thfis-implement.md)).

### 4.4 T-HFIS results (legacy — old settings)

> ⚠️ **Legacy numbers**, same caveat as §3.7: hand-crafted rules injected and seeded, TOP
> pool fitted against the hand-crafted layer 1, 12–29 rules, High 60–90, float scoring
> (`outputs/legacy_2026-09/thfis/`). Re-run `./run_thfis.sh` and replace this section.

| Split | Hand-crafted F1 / FPR | Knee F1 / FPR (rules) | Best-F1 F1 / FPR (rules) |
|---|---|---|---|
| Primary | 0.6056 / 0.0140 | 0.8718 / 0.0049 (15) | 0.9280 / 0.0201 (23 = 9+2+3+9) |
| Round-holdout | 0.3548 / 0.0126 | 0.7848 / 0.0034 (14) | 0.8956 / 0.0244 (24 = 9+3+3+9) |
| LOSO mean ± std | 0.572 ± 0.104 | **0.787 ± 0.158** | – |

LOSO per fold (data-driven vs hand-crafted): S1 0.796/0.694 · S2 0.512/0.450 · S3 0.843/0.704 ·
S4 0.926/0.462 · S5 0.978/0.512 · S6 0.669/0.612.

- The hand-crafted hierarchy is weak: 0.61 on primary, and it collapses to 0.35 on a new round.
- Data-driven selection fixes that. The selected hierarchy beats its hand-crafted base in all six LOSO folds.
- The best-F1 hierarchy keeps 9 of its 25 hand-crafted rules, so its overlap with the original design is much higher than CARS's.

---

## 5. CARS vs T-HFIS and why CARS was chosen

> ⚠️ The numbers in this table and in reasons 1–2 are the legacy results of §3.7 and §4.4.
> The design rows (inference, firmware cost, consequent fitting, interpretability) still hold.

| | CARS (flat) | T-HFIS (hierarchical) |
|---|---|---|
| Inference | one 7-input Sugeno unit | four chained Sugeno units |
| Candidate pool | enum ≤4 terms + Wang–Mendel (legacy: 701 incl. 18 injected expert) | full per-unit enumeration (legacy: 78 incl. 25 injected hand-crafted) |
| Primary, best-F1 | 0.9278 / FPR 0.0218 (23 rules) | 0.9280 / FPR 0.0201 (23 rules) |
| Primary, knee | **0.9153** / FPR 0.0061 (15) | 0.8718 / FPR 0.0049 (15) |
| Round-holdout, knee | **0.8317** (15) | 0.7848 (14) |
| LOSO mean F1 (knee) | **0.836 ± 0.131** | 0.787 ± 0.158 |
| Firmware cost | 1 integer divide, 1 rule loop | 4 divides, 4 loops, re-fuzzification of 3 intermediates |
| Consequent fitting | exact: each rule's certainty grade uses the real inputs | approximate for TOP: fitted against a reference layer 1 (all generated layer-1 rules on) that differs from the selected one |
| Interpretability | each rule reads directly in terms of $v_1..v_7$ | TOP rules read in terms of abstract RA/SI/CX scores |
| Overlap with hand-crafted base | ~chance (1/18) | substantial (9/25) |

**Why CARS was adopted.**

1. **Same accuracy ceiling.** At the same rule count (23), both methods reach F1 ≈ 0.928. The hierarchy buys no accuracy at the top of the front.
2. **Better generalisation for the compact bases.** At about 15 rules, CARS is ahead on primary (+0.044), round-holdout (+0.047) and the LOSO mean (+0.049). These compact bases are the ones that fit the mote budget comfortably.
3. **Simpler and cheaper on the mote.** CARS has one weighted average and a single divide. It needs no intermediate re-fuzzification and has no layer-1/TOP coupling to keep consistent.
4. **Cleaner method.** Every CARS consequent is fitted on the inputs the rule actually sees. The T-HFIS TOP consequents are fitted on a reference signal, which is an approximation. It shows up as a selected TOP rule with support 0.000 (T4 in the primary best-F1 base).
5. **Direct readability.** A CARS rule such as "IF $v_2$ is H AND $v_3$ is H AND $v_5$ is L AND $v_6$ is L THEN VH" can be checked against protocol behaviour without decoding intermediate scores.

**Where T-HFIS is stronger:**

- It improves most over its own hand-crafted baseline (it never loses a LOSO fold to it).
- It stays closer to the taxonomy-derived design.

If the argument were "refine an expert design" rather than "select the best rules from
data", T-HFIS would be the natural choice.

---

## 6. Limitations to state with the CARS results

1. **Unseen attack types.** In the legacy runs, LOSO F1 fell to 0.65–0.69 on S2 and S6 (and the hand-crafted R1–R18 did better on S1/S2). CARS partly specialises to the attack types it was trained on. Report LOSO mean ± std alongside the primary number, not the primary number alone.
2. **Best-F1 pick uses the test split** (§3.4). The knee numbers are the clean held-out numbers.
3. **Primary split autocorrelation.** Rows are shuffled within runs. The round-holdout and LOSO splits bound the effect.
4. **Seeds.** The split, initial population and GA randomness are all fixed by one seed. Report results over several seeds (`SEEDS="1 2 3 4 5" ./run_cars.sh` gives mean ± std in `SUMMARY.md`).
5. **Fixed membership functions.** Rules are selected under High = [50, 80], the firmware's setting; a base selected under one MF setting does not transfer to another. Do not tune MFs and rules on the same split.
6. **No $z=50$ for generated rules.** This is a side effect of the 0.15 confidence margin (§3.2).
7. **No built-in comparison with a hand-crafted base.** The code scores only data-selected bases. A comparison with R1–R18 (or $K_0$) has to be made separately, with the same test splits and arithmetic.
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
