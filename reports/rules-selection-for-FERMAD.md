# Offline Fuzzy Rule Selection for FERMAD — Technical Reference

Complete technical description of the CARS rule-selection pipeline as implemented in this
repository (`./run_cars.sh`, `methods/cars/`, `common/`), the justification for each design
decision, and the literature each decision rests on. T-HFIS, the hierarchical alternative,
reuses the same core; it is described in `methods/thfis/README.md` and
`reports/offline-rule-selection-methods.md` §4.

The pipeline replaces the claim *"the rule base was designed by expert judgement"* with a
reproducible procedure: generate a large candidate rule pool from data, search the space of
rule subsets under explicit accuracy and cost objectives, and export the chosen subset as
integer C for the mote. **No hand-crafted rules are used at any stage** — not in the pool,
not in the initial population, and not as a baseline.

> Written from the code as of 2026-10-22. Line references are to that version.

---

## 1. Notation and data model

| Symbol | Meaning |
|---|---|
| $v_1 \dots v_7$ | The seven evidence features emitted per IDS detection event, integers on a $0$–$100$ scale |
| $\mu_L, \mu_M, \mu_H$ | Membership functions Low / Medium / High |
| $A_r$ | Antecedent of rule $r$: a 7-tuple over $\{0,1,2,3\}$ = {don't-care, L, M, H} |
| $z_r$ | Singleton consequent of rule $r$, in $\{0, 25, 50, 75, 100\}$ |
| $w_r(x)$ | Firing strength of rule $r$ on event $x$ |
| $AC(x)$ | Attack Confidence, the defuzzified output in $[0,100]$ |
| $\tau$ | Detection threshold (`AC_THR`, default 65 = `FUZZRID_TAU_Q_PCT`) |
| $S$ | A selected rule subset; the thing being optimised |

A rule is the pair $(A_r, z_r)$. A **rule base** is a subset $S$ of the candidate pool.
Selection operates on $S$, never on the membership functions (§11.3).

| Feature | Evidence | Role |
|---|---|---|
| $v_1$ | Rank monotonicity violation | inculpatory |
| $v_2$ | Trickle resets | inculpatory |
| $v_3$ | CUSUM rank drift / spike | inculpatory |
| $v_4$ | Rank jump vs. link cost | inculpatory |
| $v_5$ | Residual sign-flip count | inculpatory |
| $v_6$ | Mobility index | **exculpatory** (explains benign rank changes) |
| $v_7$ | Two-hop residual (forgery corroboration) | inculpatory |

---

## 2. Stage 0 — Entry point and configuration

The whole pipeline runs with one command, `./run_cars.sh`. It reads every setting from
**`config.sh`** (shared with `./run_thfis.sh`, so both methods always use the same values),
writes a new run folder `outputs/cars/run_<date>_<time>/`, and calls, per seed:

| Step | Script | Produces |
|---|---|---|
| select | `methods/cars/run_real_selection.py` | `seed_<s>/primary/`, `seed_<s>/round_holdout/` |
| loso | `methods/cars/run_loso.py` | `seed_<s>/loso/S1..S6/` |
| finalize | `methods/cars/finalize_selection.py` (×2) | `selected_rules_best_f1.{txt,c}` in primary and round_holdout |
| summary | `scripts/summarize_run.py` | `SUMMARY.md` |

The shared plumbing (argument parsing, run folder, `config.txt`, check and parse steps) is
`scripts/run_common.sh`. Every run writes **`config.txt`** with all settings and the git
commit (marked `-dirty` if there are uncommitted changes), and `--from <step>` resumes a run
by reloading that file, so finalize always uses the same seed, sample size and split as the
selection it re-picks from.

Two settings decide what the scores mean, and a rule base selected under one value is not
transferable to another:

- **`MF_HIGH`** (`--mf-high`, default `50,80`) — the High-set breakpoints (§4.1). They must
  match the firmware's `mu_H`.
- **`ARITH`** (`--arith`, default `int`) — the arithmetic used for every score (§4.3).

Each Python entry script calls `set_arithmetic(args.arith)` right after parsing its
arguments, and builds `MFConfig(high=(c, d))` from `--mf-high`.

---

## 3. Stage 1 — Loading and labelling (`common/real_data.py`)

### 3.1 Corpus layout

`load_real_events` ([`real_data.py:65`](../common/real_data.py#L65)) walks

```
data/processed/{mobile,static}/r{1,2,3}/{3,6,9}/<sim-id>-S<k>-exp<id>[-mobile]-<round>.csv
```

and takes four labels from the path: environment (mobile/static), round (r1–r3, independent
simulation repetitions), attacker count (3/6/9) and attack type (S1–S6, from the filename).
Rows with `type == detection` are kept and $v_1..v_7$, `t`, `src`, `mote_id` are coerced to
numbers; unparseable rows are dropped.

**Attacker IDs** come from the attacker-count folder: 3 → {29–31}, 6 → {26–31},
9 → {23–31} (`ATK_NODES_BY_COUNT`). They match the `Starting 2H-FuzzRID attacker` boot lines in
every raw log.

**Static de-duplication.** The static simulation is deterministic: static r1, r2 and r3 are
byte-identical files (checked by hash). Only static r1 is loaded; otherwise every static row
would be counted three times and bias support, confidence and the split balance. Mobile
rounds differ in their random mobility realisation and are all loaded. Of the 108 CSVs,
72 are used.

### 3.2 The labelling rule

```python
y = 1  iff  src ∈ attackers(atkcount)  AND  t >= 300      # t in seconds
```

Ground truth comes from simulation knowledge of which motes are malicious, matching the
convention used by `compute_metrics.py` so that offline selection and online evaluation agree.
The attack phase start is a fixed 300 s (`atk_start_s`).

### 3.3 Two deliberate row-exclusion policies

Both are on by default, and both are methodologically load-bearing:

1. **Attacker observers** (`drop_attacker_observers`) — rows whose *observer* (`mote_id`) is
   an attacker are dropped. An attacker does not run the IDS honestly; its observations are
   not evidence the real system would act on.
2. **Pre-attack attacker rows** (`drop_prelaunch_attacker_rows`) — observations *of* an
   attacker before 300 s are dropped, not labelled benign. Before launch the attacker behaves
   honestly, so its evidence looks benign: $y=0$ would be correct but useless, $y=1$ would
   be label noise. Dropping the rows avoids forcing the optimiser to fit an unlearnable
   region. This removes 9,577 rows.

> **Justification.** Both avoid what Arp et al. call *spurious correlations* and *biased
> parameter selection* — constructing a training distribution the deployed system will never
> see [8].

In the raw logs, 646 of the 648 attacker activations (`[ATK-LAUNCHED]`) fall between 200 s
and 299 s, so attacker rows between activation and 300 s are among the dropped ones (moving
the start to 200 s would add 1,874 attack rows, +2.2 %). Two activations occur at 329 s and
330 s, so up to 30 s of those attackers' honest behaviour is labelled malicious.

**Clean corpus:** 388,338 detection events, 83,781 attack / 304,557 benign (21.6 % positive).

### 3.4 Validation splits

Each split is a complete, independent run of pool building and NSGA-II on its own training
partition:

| Split | Function | Train | Test | Question |
|---|---|---|---|---|
| **Primary** | `stratified_scenario_split` ([`real_data.py:153`](../common/real_data.py#L153)) | 70 % of each scenario, shuffled (271,834 events) | remaining 30 % (116,504) | held-out accuracy |
| **Round-holdout** | `round_holdout_split` ([`real_data.py:170`](../common/real_data.py#L170)) | mobile r1+r2, static r1 (292,649) | mobile **r3** (95,689) | transfer to a fresh mobility realisation |
| **LOSO** | `scenario_holdout_split` ([`real_data.py:179`](../common/real_data.py#L179)) | 5 of 6 attack types | the 6th | transfer to an **unseen attack type** |

> ⚠️ **The primary split is optimistic.** Shuffling *within* a scenario puts consecutive,
> strongly autocorrelated events from the same node, attack window and simulation run on both
> sides of the split, so the held-out set is not independent [8]. Round-holdout and LOSO exist
> to measure how much; report them alongside the primary number, never the primary number alone.

### 3.5 The training sample

Pool building and NSGA-II fitness do not use the whole training partition. `stratified_subsample`
([`real_data.py:193`](../common/real_data.py#L193)) draws `TRAIN_SAMPLE` events (40,000 for
select and finalize, 30,000 for LOSO) without replacement from every
(scenario × environment × attacker count × round) cell, in proportion to cell size and with at
least one event per cell. This keeps the firing matrix tractable. **All reported test metrics
use the full test partition.**

---

## 4. Stage 2 — The fuzzy inference core (`common/fuzzy.py`)

The module re-implements the on-device inference of `fuzzrid-fuzzy.c` (Algorithm 2) in NumPy,
so that offline selection scores the rule base with the arithmetic the Z1/MSP430 runs.

### 4.1 Membership functions

`MFConfig` ([`fuzzy.py:55`](../common/fuzzy.py#L55)), defaults `low=(20,50)`, `med=(20,50,80)`,
`high=(50,80)`:

- **Low (L)**: trapezoidal, $\mu_L(v) = 100$ on $[0, 20]$, decaying linearly to 0 at $v = 50$.
- **Medium (M)**: triangular, 0 at $v = 20$, peak 100 at $v = 50$, 0 at $v = 80$.
- **High (H)**: trapezoidal, 0 at $v = 50$, rising linearly to 100 at $v = 80$, saturated on $[80, 100]$.

These are the same sets as `mu_L`/`mu_M`/`mu_H` in the firmware's `fuzzrid-fuzzy.c` — the
standard three-term linguistic partition of a normalised variable [12]. Before integer
truncation they form a strong (Ruspini) partition: L + M = 1 on $[20,50]$ and M + H = 1 on
$[50,80]$, the usual interpretability requirement [7]. `--mf-high 60,90` reproduces the
earlier High set, which left a $[50,60]$ band where only Medium was non-zero.

### 4.2 Firing strength

`firing_matrix` ([`fuzzy.py:93`](../common/fuzzy.py#L93)):

$$w_r(x) = \min_{i \,:\, A_r[i] \neq 0} \mu_{A_r[i]}(x_i)$$

The **minimum t-norm** (Zadeh's conjunction [12], as in Mamdani-style inference [13]) over the
*specified* terms only; don't-care positions are skipped, so a 2-term rule is not penalised for
the other five features. An all-don't-care antecedent fires at 0 by construction, which keeps
the degenerate "always fires" rule out of the search space.

### 4.3 Defuzzification and arithmetic

`sugeno_ac` ([`fuzzy.py:116`](../common/fuzzy.py#L116)) computes the zero-order Takagi–Sugeno
weighted average of singleton consequents [14]. Two arithmetic modes exist, selected with
`set_arithmetic` ([`fuzzy.py:29`](../common/fuzzy.py#L29)):

- **`int` (default) — the mote's arithmetic.** `_memberships_int`
  ([`fuzzy.py:77`](../common/fuzzy.py#L77)) evaluates each slope with truncating integer
  division on integer inputs, exactly as `trapezoidal_mf` / `triangular_mf` in
  `fuzzrid-fuzzy.c`, e.g. $\mu_H(v)=\lfloor 100\,(v-50)/30\rfloor$ for $50<v<80$. Memberships and
  firing strengths are integers 0–100 and
  $$AC(x)=\left\lfloor\frac{\sum_{r\in S}w_r(x)\,z_r}{1+\sum_{r\in S}w_r(x)}\right\rfloor,$$
  the firmware's `num / den` with `den = 1`.
- **`float` — the continuous model.** Memberships in $[0,1]$ and
  $AC=\sum w_r z_r / (\sum w_r+\varepsilon)$ with $\varepsilon=0.01$, the $[0,1]$-scale analogue
  of `den = 1`.

**Verification.** The firmware's own membership and inference functions were compiled from its
C source and compared with `int` mode on 200 random rule bases × 200 random evidence vectors:
identical AC on 40,000 of 40,000 cases. `float` matched exactly on only 1.15 % of them; its
decision ($AC\ge\tau$) differed on 0.14 % for flat bases, and on 4.6 % for a two-layer T-HFIS
base, where each layer's output is also truncated on the mote. With `int`, a rule base that
scores well offline cannot degrade on deployment through inference mismatch.

In both modes, when nothing fires $AC = 0$: "no evidence" maps to "no attack" rather than a
division by zero.

### 4.4 Classification

$$\hat{y}(x) = \mathbb{1}\left[AC(x) \geq \tau\right], \qquad \tau = 65 \;(\texttt{FUZZRID\_TAU\_Q\_PCT})$$

`f1_fpr` ([`optimize.py:34`](../common/optimize.py#L34)) returns $F_1$, FPR and the confusion
counts used everywhere below.

---

## 5. Stage 3 — Candidate pool construction (`common/candidates.py`)

`build_pool` ([`candidates.py:72`](../common/candidates.py#L72)) runs on the training sample
(§3.5). Two generators feed one pruned pool; they are complementary.

### 5.1 Generator A — Wang–Mendel-style cells

`wang_mendel_antecedents` ([`candidates.py:36`](../common/candidates.py#L36)):

```python
terms = M.argmax(axis=2) + 1     # per event, strongest term per feature
uniq, counts = np.unique(terms, axis=0, return_counts=True)
```

Each event is assigned to the cell of the $3^7$ grid whose terms maximise its memberships;
unique cells become full 7-term antecedents, ranked by occupancy and capped at
`wm_max_rules = 200`. This anchors the pool in the regions of input space the data actually
occupies.

> **Justification.** The classical Wang–Mendel rule-generation step [1].
>
> ⚠️ **Deviation to disclose:** Wang & Mendel give each rule a *degree* and resolve conflicts
> in a cell by maximum degree. Here conflicts are resolved by the confidence-based consequent
> (§5.3) and cells are ranked by occupancy, not degree. Call the step "Wang–Mendel-style cell
> enumeration", not Wang–Mendel verbatim.

### 5.2 Generator B — bounded exhaustive enumeration

`enumerate_antecedents` ([`candidates.py:49`](../common/candidates.py#L49)) generates every
antecedent that specifies 1 to `max_terms` (`CARS_MAX_TERMS`, default 4) features:

$$\sum_{k=1}^{4} \binom{7}{k} 3^k = 21 + 189 + 945 + 2835 = \mathbf{3990}$$

out of $4^7 - 1 = 16383$ antecedents, while guaranteeing that **every rule of ≤ 4 terms is
considered**. Enumerated rules use at most four features and Wang–Mendel rules all seven, so
the two sets cannot overlap.

> **Justification.** Wang–Mendel rules always specify all 7 features; without enumeration,
> short, readable rules would be unreachable. The 4-term bound is an interpretability
> constraint — antecedent length is a standard complexity measure in fuzzy rule selection
> [4, 7], and short rules make the base auditable.

### 5.3 Consequent assignment — certainty grade

`assign_consequents` ([`candidates.py:61`](../common/candidates.py#L61)), over the training
sample only:

$$\text{conf}(r) = \frac{\sum_{x : y=1} w_r(x)}{\sum_{x} w_r(x)}, \qquad
\text{supp}(r) = \frac{\sum_{x} w_r(x)}{n}, \qquad
z_r = \arg\min_{z \in \{0,25,50,75,100\}} \left| 100 \cdot \text{conf}(r) - z \right|$$

with ties resolved toward the smaller $z$. Confidence is the firing-weighted fraction of
attacks among the events the rule covers — Ishibuchi's *certainty grade* for classification
rules [3, 4]. Support is the mean firing strength (a fuzzy cardinality divided by $n$), not a
count of matching rows. With `ARITH=int` the firing strengths are the integer ones, so
consequents are fitted on the arithmetic the mote will run.

### 5.4 Pruning

```python
keep = (support >= min_support) & (np.abs(conf - 0.5) >= conf_margin)      # candidates.py:95
```

Defaults `CARS_MIN_SUPPORT = 0.005`, `CONF_MARGIN = 0.15`:

- **Support floor** — a rule that barely fires cannot influence $AC$ but still costs a bit in
  every chromosome; removing it shrinks the search space at no cost.
- **Confidence margin** — a rule with conf ≈ 0.5 fires equally on attack and benign events; it
  carries no discriminative information and only dilutes the weighted average.

> 📌 **Side effect.** The margin keeps only conf ≤ 0.35 or conf ≥ 0.65, which map to
> $z \in \{0,25\}$ or $z \in \{75,100\}$: **no rule in the pool can receive $z = 50$**. The
> margin is measured from 0.5, not from the training attack prior (≈ 0.21), so a rule whose
> confidence equals the prior counts as benign evidence ($z = 25$).

**On the primary split** (40,000-event sample, defaults): 3,990 enumerated + 148 Wang–Mendel
cells → **731 candidates** after pruning (20 of them Wang–Mendel), with consequents
$z = 0$: 157, $z = 25$: 89, $z = 75$: 221, $z = 100$: 264.

---

## 6. Stage 4 — Multi-objective subset selection (`common/optimize.py`)

### 6.1 Problem encoding

A chromosome is a binary vector of length $|P|$ (731 on the primary split); bit $j$ = "rule $j$
is in the base". The search space has $2^{731} \approx 10^{220}$ subsets — exhaustive search is
not available, which justifies a metaheuristic.

### 6.2 Objectives (all minimised)

`RuleSelectionProblem._evaluate` ([`optimize.py:56`](../common/optimize.py#L56)) evaluates the
firing matrix of the training sample, computed once:

| | Objective | Why it is in the model |
|---|---|---|
| $f_1$ | $1 - F_1(\text{train})$ | Detection quality under class imbalance (21.6 % attacks); plain accuracy would be dominated by the benign majority. |
| $f_2$ | $\text{FPR}(\text{train})$ | The deployment cost, kept as its own axis (below). |
| $f_3$ | $\lvert S \rvert / \texttt{max\_rules}$ | RAM/flash budget on the Z1/MSP430, and interpretability. |

Constraints: $\texttt{min\_rules} \le |S| \le \texttt{max\_rules}$ (`MIN_RULES = 12`,
`MAX_RULES = 35`). An empty chromosome gets $F=[1,1,0]$ and is marked infeasible. pymoo handles
infeasibility by constraint domination.

> **Why FPR is a separate objective.** At deployment the benign class dominates by orders of
> magnitude, so even a small FPR produces an alert stream dominated by false alarms — Axelsson's
> base-rate fallacy [9]. $F_1$ on a 1:3.6 evaluation set understates that cost. A separate FPR
> axis lets the Pareto front show the actual trade-off.

> **Why rule count is both an objective and a constraint.** The constraint enforces the hard
> memory budget; the objective applies continuous pressure toward compactness inside it, so
> among equally accurate bases the front keeps the small ones. Accuracy–complexity as a
> multi-objective trade-off is the standard formulation in genetic fuzzy rule selection [3, 4];
> rule-base size is a primary interpretability measure [7].

### 6.3 Algorithm

`run_nsga2` ([`optimize.py:83`](../common/optimize.py#L83)), NSGA-II [2] via pymoo [10]:

| Component | Setting (select / LOSO) | Note |
|---|---|---|
| Population × generations | 150 × 250 / 80 × 120 (`POP`, `GENS`, `LOSO_POP`, `LOSO_GENS`) | 37,500 / 9,600 evaluations |
| Crossover | Uniform, $p=0.9$ | Rules are an unordered set, so bit position carries no locality; one/two-point crossover would impose a false one. |
| Mutation | Bit-flip, `prob_var = 1/n_var` | ≈ 1 expected flip per individual, the standard binary-GA rate. |
| Duplicates | Eliminated | Preserves diversity on a plateau-heavy landscape. |

NSGA-II gives fast non-dominated sorting, elitism and crowding-distance diversity without a
niching parameter to tune [2].

### 6.4 Initial population

`random_population` ([`optimize.py:76`](../common/optimize.py#L76)): every individual is a
sparse random subset, each rule switched on with probability 0.02 (≈ 15 rules on a 731-rule
pool). **No rule base is seeded.** Seeding a prior rule base into generation 0 is the usual
way to inject expert knowledge into a genetic fuzzy system [6]; it is deliberately not done,
so the selected base depends on the data alone.

---

## 7. Stage 5 — Solution choice and reporting (`common/report.py`)

### 7.1 The knee pick

`knee_solution` ([`optimize.py:104`](../common/optimize.py#L104)):

```python
Fn = (F - F.min(axis=0)) / (np.ptp(F, axis=0) + 1e-12)
score = (np.array([0.6, 0.3, 0.1]) * Fn).sum(axis=1)
return int(np.argmin(score))
```

Each objective is min–max normalised over the front, then weighted 0.6 / 0.3 / 0.1 (F1 / FPR /
size) and summed; the minimum wins. An objective that is constant across the front contributes
zero. It uses the **training** objectives only — the test split is never consulted when
choosing the reported base, which is the guard against the selection-on-test critique. Output:
`selected_rules.{txt,c}`.

> ⚠️ **Naming.** The function is called `knee_solution` and the outputs say "knee-point base",
> but this is a weighted-sum scalarisation with hand-chosen weights, not a knee (a curvature
> property of the front, found e.g. with Branke et al.'s measures [11]). Describe it as a
> preference-weighted choice.

### 7.2 The best-F1 re-pick

`pick_best` ([`finalize_selection.py:38`](../methods/cars/finalize_selection.py#L38)) takes the
highest `f1_test` within the rule budget, ties within 0.002 going to fewer rules, rebuilds the
same pool (same seed, sample and split) and re-emits `selected_rules_best_f1.{txt,c}`.

> ⚠️ It chooses the base **using the test split**, so its test score is optimistic. Report the
> knee numbers as the clean held-out result; if the best-F1 base is deployed, say that it was
> validation-selected.

### 7.3 Outputs (per split)

| File | Contents |
|---|---|
| `pareto_front.csv` | One row per non-dominated base: train and test F1/FPR, test recall and precision, rule count, rule-name list. Sorted by test F1 desc, then size asc. Produced by `pareto_table` ([`report.py:29`](../common/report.py#L29)). |
| `selected_rules.txt` | The knee base, human-readable, with per-rule support and confidence (`rules_listing`, [`report.py:44`](../common/report.py#L44)) |
| `selected_rules.c` | The same base as the rule block of `fuzzrid_fuzzy_infer_ac()` |
| `selected_rules_best_f1.{txt,c}` | The best-F1 re-pick (primary and round-holdout only) |

### 7.4 C export — closing the loop

`export_c` ([`report.py:53`](../common/report.py#L53)) emits nested `min2()` calls for
multi-term antecedents and the firmware's $\varepsilon=1$ integer weighted average:

```c
/* G97(enum): v3 is H AND v6 is M -> 75 */
w[2] = min2(mu_H(v3), mu_M(v6));  zc[2] = 75;
...
uint32_t num = 0, den = 1; /* eps = 1 */
for(r = 1; r <= n; r++) { num += (uint32_t)w[r] * zc[r]; den += w[r]; }
return (uint8_t)(num / den);
```

The selected base deploys **unchanged**: there is no manual transcription step between the
evaluated and the deployed rule base, and with `ARITH=int` the offline scores are the mote's
own AC values. (T-HFIS goes one step further and exports a complete, compilable
`fuzzrid-fuzzy-hfs.c`.)

---

## 8. Justification summary — decision → rationale → citation

| Decision | Rationale | Ref |
|---|---|---|
| WM-style cell enumeration | Reference method for generating fuzzy rules from numerical data; anchors the pool in occupied regions | [1] |
| Bounded enumeration ≤ 4 terms | WM cannot express short rules; short antecedents are interpretable | [4, 7] |
| Certainty-grade consequents | Standard confidence-based consequent assignment for fuzzy classification rules | [3, 4] |
| Support/confidence pruning | Removes rules that cannot discriminate; shrinks the search space at no accuracy cost | [4] |
| Binary subset-selection encoding | Canonical formulation of fuzzy rule selection as combinatorial optimisation | [3, 5] |
| Accuracy + complexity objectives | Established accuracy–interpretability trade-off | [3, 4, 7] |
| FPR as a separate objective | Base-rate fallacy: FPR dominates operating cost at deployment class ratios | [9] |
| NSGA-II | Fast non-dominated sorting, elitism, parameter-free diversity | [2] |
| pymoo implementation | Maintained reference implementation | [10] |
| Random initial population, no seed base | The selection depends on the data alone (seeding is how prior knowledge is usually injected [6]) | [6] |
| Train-only selection, held-out reporting, round- and scenario-holdout | Avoids selection-on-test and measures leakage from autocorrelated events | [8] |
| Integer, firmware-faithful inference | Removes any evaluate/deploy mismatch | [14] |

---

## 9. Parameter reference

`config.sh` sets these for both runners; any of them can be overridden for one run
(`VAR=value ./run_cars.sh`). The CARS flag each one feeds is shown.

| Setting | Default (QUICK=1) | Flag | Effect |
|---|---|---|---|
| `SEEDS` | `42` | `--seed` | Space-separated list; one `seed_<s>/` per seed. Seeds the split, the training sample, the initial population and NSGA-II together. |
| `MIN_RULES` / `MAX_RULES` | 12 / 35 | `--min-rules` / `--max-rules` | Rule budget; `MAX_RULES` also normalises $f_3$ |
| `MF_HIGH` | `50,80` | `--mf-high` | High-set breakpoints (§4.1) |
| `AC_THR` | 65 | `--ac-thr` | Detection threshold $\tau$ |
| `ARITH` | `int` | `--arith` | `int` = mote arithmetic, `float` = continuous model (§4.3) |
| `TEST_FRAC` | 0.3 | `--test-frac` | Primary-split test fraction per scenario |
| `CONF_MARGIN` | 0.15 | `--conf-margin` | Pruning margin; see §5.4 for the $z=50$ side effect |
| `CARS_MIN_SUPPORT` | 0.005 | `--min-support` | Pruning floor |
| `CARS_MAX_TERMS` | 4 | `--max-terms` | Enumeration bound; cost is $\sum_k \binom{7}{k}3^k$ — 5 terms gives 9,093 |
| `POP` / `GENS` | 150 / 250 (20 / 5) | `--pop` / `--gens` | NSGA-II budget for select |
| `TRAIN_SAMPLE` | 40,000 (3,000) | `--train-sample` | Training sample for select and finalize (§3.5) |
| `LOSO_POP` / `LOSO_GENS` / `LOSO_TRAIN` | 80 / 120 / 30,000 (20 / 5 / 3,000) | (LOSO) | Same, for the six LOSO folds |
| `CSV_ROOT` | `data/processed` | `--csv-root` | Input corpus |
| — | 300 s | (fixed) | Attack-phase start for labelling (§3.2) |

---

## 10. How to read a run

`SUMMARY.md` lists, for every split, the rule count, test F1, FPR, recall and precision of the
knee base (and of the best-F1 base for primary and round-holdout), and the LOSO mean F1; with
several seeds every value is mean ± std. The step logs in `seed_<s>/logs/` contain the full
output, including the training-sample size, the pool size and the NSGA-II progress.

What to look at, in this order:

1. **Round-holdout and LOSO against primary.** The gap between primary F1 and the other two is
   the best available estimate of how much the primary number owes to autocorrelated events
   on both sides of the split (§3.4). A large gap means the primary number should not be
   reported on its own.
2. **LOSO per fold.** Transfer to an unseen attack type is uneven by nature; a fold far below
   the others identifies an attack type the selected rules do not cover.
3. **Precision vs recall.** A base with high precision and low recall misses attacks rather
   than raising false alarms; check which side a weak split fails on.
4. **Seed spread.** With `SEEDS="1 2 3 4 5"`, the std over seeds is optimiser variability on the
   *same* test events, not additional independent evidence.
5. **The rules themselves** (`selected_rules.txt`). Read them against protocol behaviour; a
   broad rule with very high support that maps a benign majority to VL/L can be a memorised
   description of these particular traces rather than attack semantics.

---

## 11. Threats to validity

Carry these into the paper's limitations section.

1. **Non-independent primary split** (§3.4). The primary number is optimistic by an amount
   only round-holdout and LOSO can bound. [8]
2. **Seeds.** One seed fixes the split, the training sample, the initial population and
   NSGA-II together. Run several (`SEEDS="1 2 3 4 5"`) and report the spread.
3. **MF breakpoints held fixed.** Correct as-is, but do not tune breakpoints and rules on the
   same split; nest any breakpoint tuning inside an outer fold.
4. **Simulation-derived labels.** Ground truth is attacker mote IDs in Cooja [15]; the learned
   consequents inherit the simulation's topology and mobility scope.
5. **Fixed attack start.** Labels use a fixed 300 s, while attackers activate between 200 s and
   330 s (§3.3); a per-attacker activation time would be more exact.
6. **$z = 50$ unreachable** (§5.4), a consequence of the 0.5-centred margin.
7. **"Knee" is a weighted sum** (§7.1).
8. **Pool built on a sample.** Candidates, consequents and pruning use the 40,000-event training
   sample, not the full training partition; rare-region rules can fall below the support floor
   on the sample.

---

## 12. Producing the input CSVs from Cooja

Everything above starts at `data/processed/`. This section covers the step before it: getting
from a Cooja simulation to those CSVs.

### 12.1 The chain

```
Cooja simulation (.csc)
      │  motes print one FUZZRID,DET line per IDS detection event
      ▼
serial output captured to a log file                      §12.3
      │
      ▼
scripts/parse_serial.sh → scripts/parse_serial.py         §12.4
      │  one CSV per log
      ▼
data/processed/<env>/r<k>/<3|6|9>/<...>-S<k>-exp<id>...csv   §12.2
      │
      ▼
./run_cars.sh   (or ./run_cars.sh --parse to run the parse step first)
```

### 12.2 The contract `real_data.py` enforces

**Path** — `data/processed/{mobile,static}/r{1,2,3}/{3,6,9}/<...>-S<k>-exp<id>...csv`. The
environment folder must be lowercase `mobile` or `static`; the attacker-count folder sets the
attacker IDs; the `-S<k>-` part of the filename sets the attack type. A path that does not
match raises an error.

**Header** — 18 columns, as written by `parse_serial.py`:

```
sim_ms,mote_id,src,R,Rhat,e,v1,v2,v3,v4,v5,v6,v7,AC,ML,t,type,action
```

**Only these are read:**

| Column | Meaning | Constraint |
|---|---|---|
| `type` | Event kind | Rows are filtered to `type == "detection"` |
| `mote_id` | The node **doing** the observing (runs the IDS) | Used to drop attacker-observer rows |
| `src` | The node **being** observed | Determines the label |
| `t` | Simulation time in **seconds** | Compared against 300 s; **seconds, not ms** |
| `v1`–`v7` | Evidence features | Integers on a **0–100** scale |

`sim_ms`, `R`, `Rhat`, `e`, `AC`, `ML`, `action` are not used by selection. Keep them: `AC` is
the firmware's own inference output (useful to cross-check `fuzzy.py` against the rule base
that was running when the corpus was recorded), and `R`/`Rhat`/`e` explain an evidence vector
that looks wrong.

> 📌 `mote_id` vs `src` is the easiest thing to get backwards, and it fails silently: the
> labels attach to the observer instead of the observed, and the rules train on noise that
> still scores plausibly.

### 12.3 Firmware output and capture

The firmware prints one line per detection event with the marker `FUZZRID,DET`, followed by
13 integers in this order (the format `parse_serial.py` matches):

```
FUZZRID,DET,<src>,<R>,<Rhat>,<e>,<v1>,<v2>,<v3>,<v4>,<v5>,<v6>,<v7>,<AC>,<ML>
```

and Cooja's simulation script logs it as `<time> <mote_id> <serial text>`, e.g.

```
26477931	ID:1	FUZZRID,DET,16,768,768,0,0,0,0,0,0,0,0,0,0
```

(`time` in microseconds, the mote ID bare or as `ID:<n>`). Every event is printed, not only
alerts — the pipeline needs the benign majority to measure FPR. The attacker motes announce
themselves at boot with `Starting 2H-FuzzRID attacker`, and `parse_serial.sh` reads the
attacker IDs from those lines.

> ⚠️ **Verify the unit of `time` once for your Cooja version** (`--time-unit us|ms`). Getting it
> wrong scales every `t` by 1000, which silently makes `t >= 300` always or never true.

### 12.4 `scripts/parse_serial.py` and `parse_serial.sh`

`parse_serial.py <log> <out.csv> [--time-unit us|ms]` converts one log into one CSV. It
matches the `FUZZRID,DET` payload, checks every $v_i$ is within 0–100 (and fails loudly
otherwise), writes `t = sim_ms // 1000` in seconds, and warns about lines that carry the
marker but do not match (serial truncation or a `printf` change).

> ⚠️ **Deduplication is on the whole row, never on `(sim_ms, mote_id, src)`.** One observer can
> legitimately emit several detection events for the same source within one millisecond, with
> different evidence vectors; keying on that triple would discard real observations. Only a row
> identical in every field is treated as a replay artefact, and the count is reported.
> `--no-dedup` keeps them all.

`parse_serial.sh` runs it over every `*.log` directly inside `LOG_PATH`, writing to
`OUTPUT_PATH`; `./run_cars.sh --parse` loops it over all environments, rounds and attacker
counts. Re-parsing the current logs reproduces the existing CSVs byte for byte (checked on
`mobile/r1/3`).

### 12.5 Validate before you run selection

A malformed CSV does not crash the pipeline — it produces a plausible-looking F1. The check
step of `./run_cars.sh` counts the CSVs (108 expected), and the select log prints the loader's
summary first:

```
[real_data] 108 files (0 skipped by env filter, 36 skipped as duplicate static rounds) -> 388338 detection events | attack=83781 benign=304557
```

followed by counts per scenario and per environment / round / attacker count. All six
scenarios and every round should appear, with a plausible attack share in each cell. If a
scenario or cell is missing, check the path layout (§12.2); if the attack share is zero, check
the attacker IDs and the `t` unit.

### 12.6 Data collection is where validity is decided

The autocorrelation problem of the primary split (§3.4) is not fixable in the optimiser; it is a
property of what is collected. Independent rounds (r1–r3, each with its own mobility
realisation) are what make round-holdout possible, and separate attack-type files are what make
LOSO possible. More rounds, and a topology or mobility variation per round, would strengthen both.

---

## 13. References

Bibliographic details for [1]–[4], [7]–[10] were verified against publisher/index records
in July 2026; the remainder are cited from standard bibliographies and should be checked
against your reference manager before submission.

**Fuzzy rule generation and selection**

[1] L.-X. Wang and J. M. Mendel, "Generating fuzzy rules by learning from examples,"
*IEEE Transactions on Systems, Man, and Cybernetics*, vol. 22, no. 6, pp. 1414–1427, 1992.
doi:10.1109/21.199466

[3] H. Ishibuchi, T. Murata, and I. B. Türkşen, "Single-objective and two-objective genetic
algorithms for selecting linguistic rules for pattern classification problems," *Fuzzy Sets
and Systems*, vol. 89, no. 2, pp. 135–149, 1997.

[4] H. Ishibuchi and T. Yamamoto, "Fuzzy rule selection by multi-objective genetic local
search algorithms and rule evaluation measures in data mining," *Fuzzy Sets and Systems*,
vol. 141, no. 1, pp. 59–88, 2004.

[5] H. Ishibuchi, K. Nozaki, N. Yamamoto, and H. Tanaka, "Selecting fuzzy if-then rules for
classification problems using genetic algorithms," *IEEE Transactions on Fuzzy Systems*,
vol. 3, no. 3, pp. 260–270, 1995.

[6] O. Cordón, F. Herrera, F. Hoffmann, and L. Magdalena, *Genetic Fuzzy Systems: Evolutionary
Tuning and Learning of Fuzzy Knowledge Bases*. World Scientific, 2001.

[7] M. J. Gacto, R. Alcalá, and F. Herrera, "Interpretability of linguistic fuzzy rule-based
systems: An overview of interpretability measures," *Information Sciences*, vol. 181, no. 20,
pp. 4340–4360, 2011. doi:10.1016/j.ins.2011.02.021

**Multi-objective optimization**

[2] K. Deb, A. Pratap, S. Agarwal, and T. Meyarivan, "A fast and elitist multiobjective genetic
algorithm: NSGA-II," *IEEE Transactions on Evolutionary Computation*, vol. 6, no. 2, pp. 182–197,
2002. doi:10.1109/4235.996017

[10] J. Blank and K. Deb, "pymoo: Multi-objective optimization in Python," *IEEE Access*, vol. 8,
pp. 89497–89509, 2020. doi:10.1109/ACCESS.2020.2990567

[11] J. Branke, K. Deb, H. Dierolf, and M. Osswald, "Finding knees in multi-objective
optimization," in *Parallel Problem Solving from Nature (PPSN VIII)*, LNCS 3242, pp. 722–731, 2004.

**Intrusion detection and evaluation methodology**

[8] D. Arp, E. Quiring, F. Pendlebury, A. Warnecke, F. Pierazzi, C. Wressnegger, L. Cavallaro,
and K. Rieck, "Dos and don'ts of machine learning in computer security," in *31st USENIX Security
Symposium*, 2022.

[9] S. Axelsson, "The base-rate fallacy and the difficulty of intrusion detection," *ACM
Transactions on Information and System Security*, vol. 3, no. 3, pp. 186–205, 2000.
doi:10.1145/357830.357849

**Fuzzy inference foundations**

[12] L. A. Zadeh, "Fuzzy sets," *Information and Control*, vol. 8, no. 3, pp. 338–353, 1965.

[13] E. H. Mamdani and S. Assilian, "An experiment in linguistic synthesis with a fuzzy logic
controller," *International Journal of Man-Machine Studies*, vol. 7, no. 1, pp. 1–13, 1975.

[14] T. Takagi and M. Sugeno, "Fuzzy identification of systems and its applications to modeling
and control," *IEEE Transactions on Systems, Man, and Cybernetics*, vol. 15, no. 1, pp. 116–132, 1985.

**Simulation platform**

[15] F. Österlind, A. Dunkels, J. Eriksson, N. Finne, and T. Voigt, "Cross-level sensor network
simulation with COOJA," in *31st IEEE Conference on Local Computer Networks (LCN)*, pp. 641–648, 2006.


---

## 14. How to run the CARS code

All CARS code is in `methods/cars/`, with the shared modules in `common/`. It needs Python 3
with `numpy`, `pandas` and `pymoo`; the repo-root `.venv/` has them
(`./scripts/install_lib.sh` creates it if needed).

### 14.1 One command

```bash
./run_cars.sh                          # check → select → LOSO → finalize → SUMMARY.md
QUICK=1 ./run_cars.sh                  # smoke test, ~30 s per seed
SEEDS="1 2 3 4 5" ./run_cars.sh        # multi-seed; SUMMARY.md shows mean ± std
MAX_RULES=30 ./run_cars.sh             # override any config.sh setting for one run
./run_cars.sh --parse                  # rebuild data/processed from data/raw/logs first
./run_cars.sh --out outputs/cars/run_X --from loso    # resume an earlier run
./run_cars.sh -h
```

Each run writes a new `outputs/cars/run_<date>_<time>/` (never overwriting an earlier one)
with `config.txt`, `SUMMARY.md` and `seed_<s>/{primary,round_holdout,loso/S1..S6,logs}/`.
If a step fails, the runner stops and prints the end of that step's log.

### 14.2 The individual steps

The runner calls these; they can also be run by hand **from the repo root** (their default
paths, `data/processed` and `outputs/cars`, are relative to it):

```bash
python3 methods/cars/run_real_selection.py      # primary + round-holdout
python3 methods/cars/run_loso.py                # six LOSO folds
python3 methods/cars/finalize_selection.py --split primary       --out-dir outputs/cars/primary
python3 methods/cars/finalize_selection.py --split round_holdout --out-dir outputs/cars/round_holdout
```

`finalize_selection.py` must get the same `--seed`, `--train-sample`, `--test-frac`,
`--mf-high` and `--arith` as the run it finalises, or the rebuilt pool will not match and the
mask reconstruction assert fails; `./run_cars.sh` always passes the same values.

Parsing one log by hand: `python3 scripts/parse_serial.py <sim>.log <out>.csv --time-unit us`.

### 14.3 Deploying the result

1. Open `selected_rules.c` (or `selected_rules_best_f1.c`) of the chosen split.
2. Paste its rule block into the body of `fuzzrid_fuzzy_infer_ac()` in `fuzzrid-fuzzy.c`,
   replacing the current rule block.
3. Check that the firmware's `mu_H` matches `MF_HIGH` in `config.txt`, then rebuild.

(For T-HFIS, `selected_rules.c` is a complete `fuzzrid-fuzzy-hfs.c` that is copied in
unchanged; see `reports/thfis-implement.md`.)

---

## 15. Open items

The appendix ([`Offline-rule-selection-appendix.md`](Offline-rule-selection-appendix.md)) describes
the procedure and reporting this code should support. The plan recorded here on 2026-09-30 (a
33-rule seed base $K_0$ injected into the pool and population, $U=33$, a prior-centred margin,
pre-activation events labelled benign) was **superseded on 2026-10-22**: no hand-crafted rules
are used, $U=35$, and the margin, labelling and attack start are as in §3 and §5. What remains:

1. **Results.** Run `./run_cars.sh` (and `./run_thfis.sh`) with `SEEDS="1 2 3 4 5"` and fill the
   result tables of the appendix and of `offline-rule-selection-methods.md` from `SUMMARY.md`.
2. **Deployment run.** The appendix's deployed base is selected on the full development corpus.
   The code has no such run mode yet (it runs primary, round-holdout and LOSO only).
3. **Coverage by class.** The appendix reports NF$_1$ = P(no rule fires | attack) and NF$_0$ =
   P(no rule fires | benign) for every base. The code does not compute them yet.
4. **Selection frequency.** Table A.4 needs, per antecedent–consequent pair, the fraction of
   runs in which it was in the pool ("Avail.") and selected ("Sel.") across seeds × protocols ×
   folds. Not implemented.
5. **Ablations (Table A.5).** Floating-point evaluation is available (`ARITH=float`). The others
   need code options: a prior-centred margin $|c_r-\pi|\ge m$, pre-300 s attacker events labelled
   benign instead of dropped, and a per-attacker activation time instead of the fixed 300 s.
6. **Memory budget.** Confirm on the firmware that 35 rules fit (full-image RAM and flash, the
   inference routine's worst-case stack, flash cost per rule as a function of antecedent length).
7. **Independent corpus (P4).** New Cooja runs with new seeds, and ideally a new topology or
   mobility trace, generated after every setting is frozen. They need the usual short validation
   run first.
8. **Logged-AC check.** The integer model is bit-exact with the firmware's functions (§4.3).
   Checking it against the `AC` column of the CSVs as well needs the rule base that was deployed
   when the corpus was recorded.
9. **Knee naming** (§7.1): rename `knee_solution`, or describe it as a preference-weighted choice.
