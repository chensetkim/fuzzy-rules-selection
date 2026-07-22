# Offline Fuzzy Rule Selection for 2H-FuzzRID — Technical Reference

Complete technical description of the pipeline driven by `rs/run_selection.py`, the
justification for each design decision, and the literature each decision rests on.

The pipeline exists to answer one reviewer question: **"why these 18 rules and not
others?"** It replaces the claim *"the rule base was derived by expert judgement"*
with a reproducible procedure — generate a large candidate rule pool from data,
search the space of rule subsets under explicit accuracy/cost objectives, and report
where the deployed expert base R1–R18 sits relative to the resulting Pareto front.

---

## 1. Notation and data model

| Symbol | Meaning |
|---|---|
| $v_1 \dots v_7$ | The seven evidence features emitted per IDS detection event, each on a $[0,100]$ percent scale |
| $\mu_L, \mu_M, \mu_H$ | Membership functions Low / Medium / High |
| $A_r$ | Antecedent of rule $r$: a 7-tuple over $\{0,1,2,3\}$ = {don't-care, L, M, H} |
| $z_r$ | Singleton consequent of rule $r$, in $\{0, 25, 50, 75, 100\}$ |
| $w_r(x)$ | Firing strength of rule $r$ on sample $x$ |
| $AC(x)$ | Attack Confidence, the defuzzified output in $[0,100]$ |
| $\tau$ | Detection threshold (`--ac-thr`, default 65) |
| $S$ | A selected rule subset; the thing being optimized |

A rule is the pair $(A_r, z_r)$. A **rule base** is a subset $S$ of the candidate pool.
Selection operates on $S$, never on the membership functions — see §9.2.

---

## 2. Stage 0 — Entry point and configuration

`run_selection.py:35-60`. Argparse collects two positional paths (`csv_dir`, `out_dir`)
and the tuning knobs, then two config objects are built before any work happens:

```python
atk_nodes = {int(x) for x in args.atk_nodes.split(",")} if args.atk_nodes else None
hc, hd = (int(x) for x in args.mf_high.split(","))
mf = MFConfig(high=(hc, hd))
```

`--atk-nodes` overrides `--atk-id-start`. Two labelling conventions coexist because
attacker motes are identified by ID range (`src >= 33`) in some log sets and by an
explicit list (`5,6,7,8,9,10`) in the SimFile-A layout.

`--mf-high` exists so the pre-March-2026 firmware (High set on $[50,80]$) can be
reproduced exactly; the default $[60,90]$ matches current firmware. **This is the
single most important reproducibility switch in the tool** — membership breakpoints
change every firing strength downstream, so a rule base selected under one MF
configuration is not transferable to another.

---

## 3. Stage 1 — Loading and labelling (`data.py`)

### 3.1 What happens

Every `*.csv` in `csv_dir` is read, rows with `type == detection` are kept, and the
filename prefix before the first underscore becomes the `scenario` tag
(`S1_decrease_jump_run1.csv` → `S1`). Frames are concatenated, $v_1..v_7$/`t`/`src`/
`mote_id` are coerced to numeric, and unparseable rows are dropped.

> **Where these CSVs come from:** they are produced from Cooja serial logs. The required
> schema, the capture procedure, and a reference parser are in **§12**.

### 3.2 The labelling rule

```python
y = 1  iff  src ∈ attacker_set  AND  t >= atk_start_s
```

Ground truth comes from simulation knowledge of which motes are malicious, matching
the convention already used by `compute_metrics.py` so that offline selection and
online evaluation agree.

### 3.3 Two deliberate row-exclusion policies

Both defaults are on, and both are methodologically load-bearing:

1. **`drop_attacker_observers`** — rows where `mote_id` is an attacker are dropped.
   An attacker does not run the IDS honestly; its observations are not evidence the
   real system would ever act on. Keeping them would train the rule base on a data
   distribution that cannot occur at deployment.

2. **`drop_prelaunch_attacker_rows`** — observations *of* an attacker before
   `atk_start_s` are dropped rather than labelled benign. During warm-up the
   attacker behaves honestly, so its evidence vector looks benign; labelling it
   $y=0$ is correct-but-useless, and labelling it $y=1$ would be label noise. Dropping
   it avoids forcing the optimizer to fit an unlearnable region.

> **Justification.** Both are instances of avoiding what Arp et al. call *spurious
> correlations* and *biased parameter selection* — constructing a training
> distribution that the deployed system will never see [8]. The pre-launch exclusion
> in particular prevents the classifier from being penalised on samples whose label
> is not recoverable from the features.

### 3.4 The train/test split

```python
train_test_split_by_scenario(ev, test_frac=0.3, seed=42)
```

Splitting is **stratified by scenario**: within each of S1–S6, rows are shuffled and
cut 70/30. Every attack variant therefore appears in both train and test. The
rationale is that rule selection must see all six variants — a rule base tuned on
four attack types has no reason to cover the other two.

> ⚠️ **This is the pipeline's weakest methodological point.** Shuffling *within* a
> scenario means consecutive IDS events from the same node, in the same attack window,
> of the same simulation run land on both sides of the split. Those rows are strongly
> autocorrelated, so the held-out set is not independent and test metrics are
> optimistic. Arp et al. name this pitfall directly [8]. `rs/README.md` already
> recommends the fix — **leave-one-scenario-out**: train on five variants, test on the
> sixth. Report that in the manuscript rather than the random split. See §10.

---

## 4. Stage 2 — The fuzzy inference core (`fuzzy.py`)

This module is a faithful NumPy re-implementation of the on-device integer inference
in `fuzzrid-fuzzy.c` (Algorithm 2). **The point is that offline selection evaluates
exactly the arithmetic the Z1/MSP430 firmware will run** — a rule base that scores
well here cannot degrade on deployment through inference mismatch.

### 4.1 Membership functions

With defaults `low=(20,50)`, `med=(20,50,80)`, `high=(60,90)`:

$$\mu_L(x) = \text{clip}\!\left(\frac{50-x}{30},\,0,\,1\right) \qquad
\mu_M(x) = \text{clip}\!\left(\min\!\left(\frac{x-20}{30}, \frac{80-x}{30}\right),\,0,\,1\right) \qquad
\mu_H(x) = \text{clip}\!\left(\frac{x-60}{30},\,0,\,1\right)$$

Shouldered trapezoid (L), triangle (M), shouldered ramp (H) — the standard
three-term linguistic partition of a normalized variable [12].

> ⚠️ **Note for the paper:** these sets do **not** form a Ruspini (strong) partition —
> the memberships do not sum to 1. At $x=55$: $\mu_L=0$, $\mu_M=0.833$, $\mu_H=0$, total
> $0.833$. The $[50,60]$ band is a coverage gap created by shifting High from $[50,80]$
> to $[60,90]$. This is intentional (it suppresses false High firings, which is what
> the March-2026 update targeted) but it interacts with the Sugeno denominator: in
> that band all firing strengths shrink, $\sum w_i$ falls toward $\varepsilon$, and $AC$
> becomes numerically sensitive. Worth one sentence in the MF design subsection so a
> reviewer does not raise it first. Strong-partition constraints are the usual
> interpretability requirement [7].

### 4.2 Firing strength

$$w_r(x) = \min_{i \,:\, A_r[i] \neq 0} \mu_{A_r[i]}(x_i)$$

The **minimum t-norm** (Zadeh's original conjunction [12], as used in Mamdani-style
inference [13]) over only the *specified* terms; don't-care positions are skipped, so a
2-term rule is not penalised for the other five features. A rule with an all-don't-care
antecedent fires at 0 by construction (`fuzzy.py:66-68`), which keeps the degenerate
"always fires" rule out of the search space.

### 4.3 Defuzzification

$$AC(x) = \frac{\sum_{r \in S} w_r(x)\, z_r}{\sum_{r \in S} w_r(x) + \varepsilon}, \qquad \varepsilon = 0.01$$

Zero-order Takagi–Sugeno (weighted average of singleton consequents) [14]. The
$\varepsilon$ term mirrors the firmware's `den = 1` guard on the 0..100 integer weight
scale — here weights are in $[0,1]$, so $\varepsilon = 0.01$ is the exact analogue. Its
side effect is well-defined behaviour when nothing fires: $AC = 0/\varepsilon = 0$, i.e.
"no evidence" maps to "no attack" rather than a division by zero.

### 4.4 Classification

$$\hat{y}(x) = \mathbb{1}\left[AC(x) \geq \tau\right], \qquad \tau = 65 \;(\texttt{FUZZRID\_TAU\_Q\_PCT})$$

### 4.5 The expert base R1–R18

Hard-coded at `fuzzy.py:94-114` as the canonical taxonomy-derived base from
`fuzzrid-fuzzy.c` release-1.3 rev 2.0+. Structurally these are compact rules — 1 to 5
specified terms — with $v_2$ (reputation) and $v_6$ (mobility) acting as modifiers:
$v_6$ **Low** *escalates* (R3, R6, R9: $z=75$), $v_6$ **High** *exonerates* (R13, R18:
$z \leq 25$, "mobile node, benign explanation"). R14 is the all-clear rule, R1/R2 the
single-feature strong indicators.

---

## 5. Stage 3 — Candidate pool construction (`candidates.py`)

Two generators feed one pruned pool. They are complementary, and using only one would
be a defensible reviewer objection to the other.

### 5.1 Generator A — Wang–Mendel

```python
terms = M.argmax(axis=2) + 1     # per sample, strongest term per feature
uniq, counts = np.unique(terms, axis=0, return_counts=True)
```

Each training sample is assigned to the fuzzy cell of the $3^7$ grid whose terms
maximise its memberships; unique cells become full-length 7-term antecedents, ranked by
occupancy and capped at `wm_max_rules=200`. This anchors the pool in the regions of
input space the data **actually occupies** — on the sample data, 125 cells.

> **Justification.** This is the classical Wang–Mendel rule-generation step [1], the
> reference method for extracting fuzzy rules from numerical examples.
>
> ⚠️ **Deviation to disclose:** Wang & Mendel assign each rule a *degree* and resolve
> conflicting rules in the same cell by maximum degree. Here conflict resolution is
> deferred to the confidence-based consequent assignment in §5.3, and rule degree is
> not used for ranking (occupancy count is). Describe the step as
> "Wang–Mendel-style cell enumeration", not as WM verbatim.

### 5.2 Generator B — bounded exhaustive enumeration

All antecedents specifying between 1 and `max_terms` features:

$$\sum_{k=1}^{4} \binom{7}{k} 3^k = 21 + 189 + 945 + 2835 = \mathbf{3990}$$

against a full antecedent space of $4^7 - 1 = 16383$. So `--max-terms 4` covers ~24% of
the space while guaranteeing **every rule of ≤4 terms is considered**.

> **Justification.** WM alone cannot express the deployed base: WM rules always specify
> all 7 features, whereas R1–R18 have 1–5 terms. Without this generator the expert base
> would be structurally unreachable and the comparison meaningless. The 4-term bound is
> an interpretability constraint — antecedent length is a standard complexity measure in
> fuzzy rule selection [4,7], and short rules are what make the base auditable by a
> domain expert.

### 5.3 Consequent assignment — certainty grade

For each candidate, over the **training set only**:

$$\text{conf}(r) = \frac{\sum_{x : y=1} w_r(x)}{\sum_{x} w_r(x)}, \qquad
\text{supp}(r) = \frac{\sum_{x} w_r(x)}{n}, \qquad
z_r = \arg\min_{z \in \{0,25,50,75,100\}} \left| 100 \cdot \text{conf}(r) - z \right|$$

Confidence is the firing-weighted fraction of positives — the fuzzy analogue of rule
confidence in association-rule mining, and Ishibuchi's *certainty grade* for
classification rules [3,4]. Support is mean firing strength (a fuzzy cardinality
normalized by $n$), **not** a count of matching rows.

### 5.4 Pruning

```python
keep = (support >= min_support) & (np.abs(conf - 0.5) >= conf_margin)
```

Defaults `min_support=0.005`, `conf_margin=0.15`. Two independent filters:

- **Support floor** — a rule that barely fires anywhere cannot influence $AC$, but still
  costs a bit in every chromosome. Removing it shrinks the search space at no cost.
- **Confidence margin** — a rule with $\text{conf} \approx 0.5$ fires equally on attacks
  and benign traffic. It carries no discriminative information; including it only dilutes
  the Sugeno weighted average.

> 📌 **Non-obvious consequence, worth knowing:** the margin filter keeps only
> $\text{conf} \leq 0.35$ or $\text{conf} \geq 0.65$. Mapping those through the nearest-singleton
> rule gives $z \in \{0,25\}$ or $z \in \{75,100\}$ — **no generated rule can ever receive
> $z = 50$.** The mid-level consequent is reachable only by expert rules (R12). If the
> paper claims the pipeline can rediscover the full consequent vocabulary, that claim is
> false as configured.

### 5.5 Expert-base injection

R1–R18 are appended to the pool and flagged in `expert_mask`. Generated duplicates of an
expert antecedent are dropped, **expert copy wins**, so consequents stay firmware-faithful
(an expert rule keeps its designed $z$ even where the data would suggest another).

> **Justification.** This is what makes the comparison fair. Expert and generated rules
> compete as members of one pool under one objective function, so a statement like *"the
> optimizer retained 12 of 18 expert rules"* means something. If the expert base were
> evaluated separately, any difference would confound rule quality with pool membership.

On the sample data: 3990 enumerated + 125 WM → **1056 candidates after pruning and expert
merge (18 expert)**.

---

## 6. Stage 4 — Multi-objective subset selection (`optimize.py`)

### 6.1 Problem encoding

A chromosome is a binary vector of length $|P| = 1056$; bit $j$ = "rule $j$ is in the base".
The search space is $2^{1056} \approx 10^{318}$ — exhaustive search is not available, which
is the justification for a metaheuristic rather than an exact method.

### 6.2 Objectives (all minimized)

| | Objective | Why it is in the model |
|---|---|---|
| $f_1$ | $1 - F_1(\text{train})$ | Detection quality under class imbalance (1620 attack / 3788 benign). $F_1$ balances precision and recall; accuracy would be dominated by the benign majority. |
| $f_2$ | $\text{FPR}(\text{train})$ | The deployment cost. Separated from $f_1$ deliberately — see below. |
| $f_3$ | $\lvert S \rvert / \texttt{max\_rules}$ | RAM/flash budget on the Z1/MSP430, and interpretability. |

Plus one constraint: $g = |S| - \texttt{max\_rules} \leq 0$.

> **Why FPR is a separate objective and not folded into $F_1$.** In intrusion detection
> the benign class dominates by orders of magnitude at deployment scale, so even a small
> FPR produces an alert stream dominated by false alarms — Axelsson's base-rate fallacy
> result [9]. $F_1$ computed on a 1:2.3 evaluation set systematically understates that
> cost. Exposing FPR as its own axis lets the Pareto front show the operator the actual
> trade-off instead of hiding it inside a single scalar. This objective is also what the
> High-set redesign ($[50,80] \to [60,90]$) was for, so the two design decisions are
> consistent.

> **Why rule count is an objective and not just a constraint.** It is *both* here. The
> constraint enforces the hard memory budget; the objective applies continuous pressure
> toward compactness inside the budget, so among equally accurate bases the front retains
> the small ones. Accuracy–complexity as a bi-objective trade-off is the standard
> formulation in genetic fuzzy rule selection [3,4], and rule-base size is a primary
> interpretability measure [7].

Empty chromosomes are assigned $F = [1, 1, 0]$ and marked infeasible (`optimize.py:62-65`).

### 6.3 Algorithm

NSGA-II [2] via pymoo [10]:

| Component | Setting | Note |
|---|---|---|
| Population | 120 | |
| Generations | 200 | 24,000 evaluations |
| Crossover | Uniform, $p=0.9$ | No positional meaning to bit order — rules are an unordered set, so uniform crossover is the neutral choice; one/two-point would impose a false locality. |
| Mutation | Bit-flip, `prob_var = 1/n_var` | ≈1 expected flip per individual — the standard rate for binary GAs. |
| Duplicates | Eliminated | Preserves diversity on a plateau-heavy landscape. |

NSGA-II is chosen for fast non-dominated sorting ($O(MN^2)$), elitism, and crowding-distance
diversity preservation without a niching parameter to tune [2].

### 6.4 Expert-seeded initialization — the key methodological move

```python
P = (rng.random((pop_size, pool_size)) < 0.02)   # sparse random, ~21 rules each
P[0] = expert_mask.copy()                        # the deployed base itself
for i in range(1, 10):                           # 3-bit-flip neighbours of it
    v = expert_mask.copy(); v[rng.integers(0, pool_size, 3)] ^= True; P[i] = v
```

Individual 0 **is** R1–R18; individuals 1–9 are its local neighbourhood.

> **Justification.** This guarantees the expert base is inside the search from
> generation 0, which makes the result interpretable either way it lands:
>
> - If R1–R18 survives to the final front, it is **empirically non-dominated** — the
>   optimizer had 24,000 chances to beat it and could not. That is a far stronger claim
>   than "an expert chose it."
> - If it is dominated, the dominating base is reported *and* the expert base is
>   documented as the prior that seeded the search.
>
> Without seeding, an optimizer that failed to find R1–R18 would tell you nothing —
> absence could mean "worse" or merely "not sampled." Seeding removes that ambiguity.
> This is the genetic-fuzzy-systems convention of injecting the knowledge base into the
> initial population [6].

---

## 7. Stage 5 — Solution choice and reporting (`report.py`)

### 7.1 Picking one solution from the front

```python
Fn = (F - F.min(axis=0)) / (np.ptp(F, axis=0) + 1e-12)
score = (np.array([0.6, 0.3, 0.1]) * Fn).sum(axis=1)
return int(np.argmin(score))
```

Min-max normalize each objective, then take the weighted sum, weights favouring
detection quality (0.6) over FPR (0.3) over compactness (0.1).

> ⚠️ **Naming issue to fix before submission.** The function is called
> `knee_solution` and the outputs say "knee-point base", but this is **not** a knee
> point. A knee is a curvature/bend property of the front, found by methods such as
> Branke et al.'s angle- or utility-based measures [11]. This is a *weighted-sum
> scalarization* with hand-chosen weights. Reviewers in the EMO community will catch
> the difference. Either rename it (`preference_weighted_solution`) and state the
> weights as an explicit operator preference, or implement an actual knee measure.
> Renaming is honest and sufficient — the weights *are* a legitimate way to pick, they
> just are not a knee.

Selection uses the **train** objective matrix `F` only — the test split is never
consulted when choosing which base to report. That is correct, and worth stating
explicitly in the paper, because it is the guard against the selection-on-test critique.

### 7.2 Outputs

| File | Contents |
|---|---|
| `pareto_front.csv` | One row per non-dominated base: train+test F1/FPR, recall, precision, rule count, expert overlap, rule name list. Sorted by test F1 desc, then size asc. |
| `selected_rules.txt` | The chosen base, human-readable, with per-rule support and confidence |
| `selected_rules.c` | The same base as the rule block of `fuzzrid_fuzzy_infer_ac()` |
| `overlap_report.txt` | Jaccard and expert-coverage for **every** base on the front |

### 7.3 Expert-overlap metric

$$J = \frac{|S \cap E|}{|S \cup E|}, \qquad \text{coverage} = \frac{|S \cap E|}{|E|}$$

Reported per Pareto base, which is what turns "does the optimizer agree with the
expert?" into a measurable quantity across the whole front rather than at one point.

### 7.4 C export — closing the loop

`export_c` emits nested `min2()` calls for multi-term antecedents and the same
$\varepsilon=1$ integer weighted average as the firmware:

```c
/* G28(enum): v5 is H AND v7 is L -> 100 */
w[1] = min2(mu_H(v5), mu_L(v7));  zc[1] = 100;
...
uint32_t num = 0, den = 1; /* eps = 1 */
for(r = 1; r <= n; r++) { num += (uint32_t)w[r] * zc[r]; den += w[r]; }
return (uint8_t)(num / den);
```

This is what makes the work an engineering contribution rather than an offline study:
the selected base is deployable **unchanged**, with no manual transcription step that
could introduce a discrepancy between the evaluated and the deployed rule base.

---

## 8. Justification summary — decision → rationale → citation

| Decision | Rationale | Ref |
|---|---|---|
| WM-style cell enumeration | Reference method for generating fuzzy rules from numerical data; anchors pool in occupied regions | [1] |
| Bounded enumeration ≤4 terms | WM cannot express short rules; expert base must be reachable; short antecedents = interpretable | [4,7] |
| Certainty-grade consequents | Standard confidence-based consequent assignment for fuzzy classification rules | [3,4] |
| Support/confidence pruning | Removes rules that cannot discriminate; shrinks search space at no accuracy cost | [4] |
| Binary subset-selection encoding | Canonical formulation of fuzzy rule selection as combinatorial optimization | [3] |
| Accuracy + complexity objectives | Established accuracy–interpretability trade-off formulation | [3,4,7] |
| FPR as a separate objective | Base-rate fallacy: FPR dominates operational cost in IDS at deployment class ratios | [9] |
| NSGA-II | Fast non-dominated sorting, elitism, parameter-free diversity | [2] |
| pymoo implementation | Maintained reference implementation | [10] |
| Expert-seeded population | Makes non-domination of the expert base a testable claim, not an absence of evidence | [6] |
| Train-only selection, held-out reporting | Avoids selection-on-test; standard security-ML hygiene | [8] |
| Firmware-faithful inference | Removes evaluate/deploy mismatch | [14] |

---

## 9. Parameter reference

| Flag | Default | Effect |
|---|---|---|
| `--atk-id-start` | 33 | Attackers are `src >= N` |
| `--atk-nodes` | — | Explicit attacker list; **overrides** `--atk-id-start` |
| `--atk-start-s` | 300 | Attack launch time (`FUZZRID_T_WARM_S`) |
| `--ac-thr` | 65.0 | Detection threshold $\tau$ (`FUZZRID_TAU_Q_PCT`) |
| `--max-terms` | 4 | Enumeration bound; **cost is $\sum_k \binom{7}{k}3^k$ — raising to 5 gives 8,463** |
| `--max-rules` | 30 | Hard cap $|S|$, and the $f_3$ normalizer |
| `--min-support` | 0.005 | Pruning floor |
| `--conf-margin` | 0.15 | Pruning margin; see §5.4 for the $z=50$ side effect |
| `--pop` / `--gens` | 120 / 200 | NSGA-II budget = 24,000 evaluations |
| `--seed` | 42 | Seeds split, pool init, and NSGA-II |
| `--test-frac` | 0.3 | Per-scenario holdout fraction |
| `--mf-high` | `60,90` | High-set breakpoints; `50,80` = pre-Mar-2026 base |

---

## 10. Observed behaviour on `sample_csv/` and how to read it

Run: `--atk-nodes 5,6,7,8,9,10 --atk-start-s 300 --ac-thr 65`, defaults otherwise.

```
[data]  5408 detection events | attack=1620 benign=3788 | scenarios=[S1..S6]
[pool]  enumerated=3990  wang-mendel=125  after pruning+expert merge=1056 (18 expert)
[expert R1-R18] test F1=0.9101  FPR=0.0017  recall=0.8386  precision=0.9950
[done]  selected base: 8 rules | test F1=0.9871  FPR=0.0000 | expert rules kept=1/18
```

A control run at `--gens 2 --pop 8` (essentially the seeded population, unoptimized)
gives the contrast that matters:

| | 200 gens × 120 pop | 2 gens × 8 pop |
|---|---|---|
| test F1 | 0.9871 | 0.8881 |
| test FPR | 0.0000 | 0.0009 |
| base size | 8 | 21 |
| **expert rules kept** | **1 / 18** | **18 / 18** |

**Read this result with suspicion, not satisfaction.** Two generations retain the entire
expert base; two hundred discard 17 of 18 rules to gain ≈0.08 F1 and reach a *perfect*
zero-FPR score. Combined with §3.4 — one simulation run per scenario, split by random
shuffle within scenario — the most likely explanation is that the search is exploiting
autocorrelation between near-identical events that straddle the split, not discovering
better attack semantics. The single surviving expert rule is R1 ($v_1$ High → VH), the
most general rule in the base; the generated rules that replace it include
`IF v1 L AND v2 L AND v3 L AND v7 L THEN VL` at support 0.561, which is close to a
memorized description of the benign majority of these particular traces.

**Before any of this goes in the manuscript**, re-run under leave-one-scenario-out. If
the expert-overlap number holds up there, it is a real finding; if it collapses toward
the expert base, the random-split number was leakage. Either way you learn which of the
two publishable outcomes in `rs/README.md` §"How to use the result" you actually have.

---

## 11. Threats to validity

Carry these into the paper's limitations section.

1. **Non-independent train/test split** (§3.4). The headline number is optimistic by an
   unquantified margin. Leave-one-scenario-out is the fix. [8]
2. **Single seed.** All reported numbers use `--seed 42`, which fixes the split, the
   initial population, *and* NSGA-II's stochasticity together. Run `--seed 1..10` and
   report the front's variation; a single evolutionary run is not evidence.
3. **MF breakpoints held fixed.** Correct as-is — but do *not* later tune breakpoints and
   rules on the same split in the same run, or the circular-threshold critique the
   pipeline was built to answer reappears one level down. Nest it: outer CV fold → tune → evaluate.
4. **Simulation-derived labels.** Ground truth is attacker mote ID in Cooja [15]; the
   learned consequents inherit the single-topology scope already declared as a limitation.
5. **No Ruspini partition** (§4.1), and **$z=50$ unreachable for generated rules** (§5.4).
   Both are consequences of the current configuration, not bugs, but both should be stated
   rather than discovered by a reviewer.
6. **"Knee" is a weighted sum** (§7.1). Rename or reimplement.

### Minor code issues (cosmetic, no effect on results)

- `run_selection.py:80` — `e_ants, e_z` are assigned from `expert_arrays()` and never
  used; the expert data actually consumed comes from `pool[...]`. Dead assignment.
- `run_selection.py:23` — `import numpy as np` is unused.
- `run_selection.py:27,31` — `fuzzy` is imported twice on separate lines.

---

## 12. Producing the input CSVs from Cooja

Everything above starts at `csv_dir`. This section covers the step before it: getting
from a Cooja simulation to the `*.csv` files `data.py` consumes.

> ⚠️ **Repository gap.** `parse_serial.py` is referenced by `data.py`, `rs/README.md`
> and `make_synth.py`, but **it is not in this repository** — neither is the firmware
> (`fuzzrid-fuzzy.c`) nor any `.csc` simulation file. `sample_csv/` contains its output,
> not the tool. What follows specifies the contract the loader enforces (verified
> against the code and the sample files) and gives a reference implementation. The
> regexes in §12.5 must be aligned with whatever your firmware actually prints.

### 12.1 The chain

```
Cooja simulation (.csc)
      │  motes print one line per IDS detection event
      ▼
serial output captured to a log file        ......... §12.4
      │
      ▼
parse_serial.py  →  one CSV per scenario run ......... §12.5
      │
      ▼
sample_csv/S<k>_<variant>_run<n>.csv        ......... §12.2
      │
      ▼
run_selection.py <csv_dir> <out_dir>
```

### 12.2 The contract `data.py` enforces

**Filename** — `<SCENARIO>_<anything>.csv`. The scenario tag is the prefix **before the
first underscore** (`data.py:47`): `S1_decrease_jump_run1.csv` → `S1`. This tag is what
the per-scenario stratified split groups on, so it is functional, not decorative. Files
sharing a prefix merge into one scenario group — that is how you add repeat runs.

**Header** — 18 columns, exact order as written by the sample files:

```
sim_ms,mote_id,src,R,Rhat,e,v1,v2,v3,v4,v5,v6,v7,AC,ML,t,type,action
```

**Only these are actually read** (`data.py:26,43,53`):

| Column | Meaning | Constraint |
|---|---|---|
| `type` | Event kind | Rows are filtered to `type == "detection"`; others discarded |
| `mote_id` | The node **doing** the observing (runs the IDS) | Used to drop attacker-observer rows |
| `src` | The node **being** observed | Determines the label — attacker set is matched against `src` |
| `t` | Simulation time in **seconds** | Compared against `--atk-start-s`; **seconds, not ms** |
| `v1`–`v7` | Evidence features | Numeric on a **0–100** scale |

`sim_ms`, `R`, `Rhat`, `e`, `AC`, `ML`, `action` are **not consumed by the selection
pipeline**. Keep them anyway: `AC` is the firmware's own inference output, which is what
lets you cross-check that the offline core in `fuzzy.py` reproduces the on-device result
(§4), and `R`/`Rhat`/`e` are needed to debug an evidence vector that looks wrong.

> 📌 `mote_id` vs `src` is the single easiest thing to get backwards, and it fails
> silently — the labels attach to the observer instead of the observed, and you train on
> noise that still scores plausibly. See the check in §12.6.

**Sanity anchors from the shipped sample:** 6 files, ~920–930 rows each, 294 rows per
file with `src ∈ {5..10}`, all rows `type=detection`, `t = sim_ms / 1000`, `v` values
integer in 0–100. 5552 raw rows → 5408 after the exclusions in §3.3.

### 12.3 Instrumenting the firmware

Emit **one line per detection event, already comma-separated**, with a fixed marker
token. Parsing free-form log prose is where this step usually breaks; printing the CSV
payload directly from the mote removes the ambiguity.

```c
/* in the IDS detection path, after AC is computed */
printf("FUZZRID,DET,%u,%d,%d,%d,%u,%u,%u,%u,%u,%u,%u,%u,%u\n",
       src_id, R, Rhat, e,
       v1, v2, v3, v4, v5, v6, v7,
       ac, ml);
```

Practical constraints on the Z1/MSP430 that shape this format:

- **Integers only.** Contiki's `printf` on MSP430 has no float support in the default
  build, and `%ld` pulls in extra library code. Keep every field a scaled integer — the
  $v_i$ are already 0–100 integers.
- **Watch the line length.** Contiki's serial output buffer is small; a long line can be
  split across two writes and arrive as two log lines. The format above is ~60 chars,
  comfortably inside the limit. If you add fields, re-check.
- **Do not print `mote_id`.** Cooja already attaches the originating mote to every serial
  line (§12.4), which is more trustworthy than a self-reported ID.
- **Print unconditionally, not only when `AC >= τ`.** The pipeline needs the benign
  majority — logging only alerts would leave you with positives only and no FPR signal.

### 12.4 Capturing serial output from Cooja

The version-stable route is a **simulation script** (Cooja's *Simulation script editor*
plugin), because it works identically in GUI and headless mode and timestamps every line:

```js
TIMEOUT(1800000);            /* 1,800,000 ms of SIMULATED time = 1800 s */

while (true) {
    log.log(time + " " + id + " " + msg + "\n");
    YIELD();
}
```

`msg` is the serial line, `id` is the mote that emitted it (→ `mote_id`), `time` is the
simulation clock.

> ⚠️ **Verify the unit of `time` once, for your Cooja version.** It is microseconds in
> the Cooja versions I am aware of, but this has not been consistent across the Contiki
> 2.x / 3.x / Contiki-NG lineage, and `TIMEOUT` takes *milliseconds* in the same script —
> so the two are not in the same unit. Getting it wrong scales every `t` by 1000, which
> silently makes `t >= atk_start_s` either always or never true. One-line check: run for
> a known simulated duration and confirm the last timestamp matches. §12.5 exposes this
> as the `--time-unit` flag.

Headless invocation differs by generation — check which applies to your tree:

```bash
# Contiki-NG
cd $CONTIKI/tools/cooja
./gradlew run --args="--no-gui --logdir=$OUT $SIM.csc"

# Legacy Cooja (Contiki 2.x/3.x)
java -mx512m -jar $CONTIKI/tools/cooja/dist/cooja.jar -nogui=$SIM.csc -contiki=$CONTIKI
```

The GUI alternative — *Mote output* window → **File ▸ Save to file** — is fine for a
one-off, but it is a manual step in the middle of a pipeline you are documenting as
reproducible. Prefer the script.

**Run one simulation per (scenario, seed).** Change the Cooja random seed between runs;
each run becomes its own `_run<n>` file. §12.7 explains why this matters more than it
looks.

### 12.5 Reference `parse_serial.py`

Converts one captured log into one schema-conformant CSV. **The full script is
`rs/parse_serial.py`** — the listing below is abridged to the parts you must adapt.
Round-trip verified against `sample_csv/S1_decrease_jump_run1.csv`: re-encoded as a
synthetic Cooja log and re-parsed, it reproduces all 931 rows byte-identically.

```python
#!/usr/bin/env python3
"""parse_serial.py -- Cooja serial log -> rule-selection event CSV.

Usage:
    python3 parse_serial.py sim.log sample_csv/S1_decrease_jump_run1.csv \
        [--time-unit us|ms] [--atk-nodes 5,6,7,8,9,10]
"""
import argparse, csv, re, sys
from pathlib import Path

COLS = ["sim_ms", "mote_id", "src", "R", "Rhat", "e",
        "v1", "v2", "v3", "v4", "v5", "v6", "v7", "AC", "ML",
        "t", "type", "action"]

# Line as written by the Cooja script in 12.4: "<time> <mote_id> <serial text>"
LOG = re.compile(r"^\s*(\d+)\s+(\d+)\s+(.*)$")

# Firmware payload from 12.3.  <<< ALIGN THIS WITH YOUR printf >>>
EVT = re.compile(
    r"FUZZRID,DET,"
    r"(?P<src>\d+),(?P<R>-?\d+),(?P<Rhat>-?\d+),(?P<e>-?\d+),"
    r"(?P<v1>\d+),(?P<v2>\d+),(?P<v3>\d+),(?P<v4>\d+),"
    r"(?P<v5>\d+),(?P<v6>\d+),(?P<v7>\d+),"
    r"(?P<AC>\d+),(?P<ML>\d+)\s*$")

V = [f"v{i}" for i in range(1, 8)]


def parse(log_path, time_unit="us", dedup=True):
    for ln in Path(log_path).read_text(errors="replace").splitlines():
        m = LOG.match(ln)
        if not m:
            continue
        stamp, mote_id, payload = m.groups()
        e = EVT.search(payload)
        if not e:
            if "FUZZRID" in payload:       # marker present but shape wrong
                malformed += 1             # -> truncated line or format drift
            continue
        d = e.groupdict()
        sim_ms = int(stamp) // 1000 if time_unit == "us" else int(stamp)

        for k in V:                        # fail loudly on scale errors
            if not 0 <= int(d[k]) <= 100:
                raise ValueError(f"{k}={d[k]} outside 0..100 -- features must be "
                                 f"normalised before printing (line: {ln[:80]})")

        row = {"sim_ms": sim_ms, "mote_id": int(mote_id), ...,
               "t": sim_ms // 1000,        # SECONDS -- data.py compares against it
               "type": "detection", "action": ""}

        if dedup:                          # see the warning below
            key = tuple(row[c] for c in COLS)
            if key in seen:
                dropped += 1
                continue
            seen.add(key)
        rows.append(row)
    return rows
```

> ⚠️ **Deduplicate on the whole row, never on `(sim_ms, mote_id, src)`.** That triple is
> not unique in real data: in the shipped sample, mote 30 emits two detection events for
> src 5 at t=1598 with *different* evidence vectors (v1=87 and v1=82), and mote 21 does
> the same for src 15 at t=195. Keying on the triple silently discards real observations
> — it cost 2 of 931 rows on one file before this was caught. Only a row identical in
> **every** field is a genuine replay artefact, and the script reports how many it drops
> rather than discarding them quietly. Pass `--no-dedup` to keep them all.

Driving it over a batch of runs:

```bash
for s in S1_decrease_jump S2_decrease_slow S3_increase_jump \
         S4_increase_slow S5_fluctuation S6_forge_2hop; do
  for n in 1 2 3; do
    python3 rs/parse_serial.py "logs/${s}_run${n}.log" \
        "sample_csv/${s}_run${n}.csv" --atk-nodes 5,6,7,8,9,10
  done
done
```

### 12.6 Validate before you run selection

A malformed CSV does not crash the pipeline — it produces a plausible-looking F1. Check
explicitly:

```python
import pandas as pd, glob
for f in sorted(glob.glob("sample_csv/*.csv")):
    d = pd.read_csv(f)
    v = d[[f"v{i}" for i in range(1, 8)]]
    print(f"{f}: rows={len(d)} t={d.t.min()}..{d.t.max()} "
          f"v_range={v.values.min()}..{v.values.max()} "
          f"atk_src={d.src.isin(range(5, 11)).sum()} "
          f"atk_obs={d.mote_id.isin(range(5, 11)).sum()} "
          f"post_warmup={(d.t >= 300).sum()}")
```

What each number has to look like, and what it means when it doesn't:

| Check | Expected | If violated |
|---|---|---|
| `v_range` | within `0..100` | Features not normalised; memberships saturate and every rule fires at 0 or 1 |
| `t` max | ≈ simulated duration in **seconds** (e.g. 1800) | If it is ~1.8M, `t` is in ms — every row lands post-warm-up and `--atk-start-s` stops discriminating |
| `atk_src` | > 0, roughly a third of rows | Zero means wrong attacker set, or `src`/`mote_id` swapped |
| `atk_obs` | > 0 but small | Zero is *suspicious*: these rows should exist and then be dropped by §3.3. Zero suggests attackers never appear as observers, i.e. `mote_id` may be misparsed |
| `post_warmup` | most but not all rows | All rows means `t` is wrong; no rows means the warm-up never ended |
| rows per file | comparable across scenarios | A short file means the simulation ended early or the log was truncated mid-capture |

Then confirm the loader agrees, before spending 24,000 evaluations on bad data — the
`[data]` line is printed within a second or two of startup:

```
[data] 5408 detection events | attack=1620 benign=3788 | scenarios=['S1'...'S6']
```

All six scenarios present, and a benign:attack ratio in a plausible range. If a scenario
is missing, its filename prefix is wrong (§12.2).

### 12.7 Data collection is where the §11 validity problems get fixed

The two weaknesses in §3.4 and §11 are **not fixable in the optimizer** — they are
properties of what you collect:

1. **Multiple independent runs per scenario.** The shipped `sample_csv/` has exactly one
   run per scenario (`_run1`), which is why a random within-scenario split puts
   autocorrelated events from the same attack window on both sides. Generating
   `_run2`, `_run3`, … with different Cooja seeds gives genuinely independent samples and
   lets you split by *run* rather than by row — the correct unit of independence.
2. **Leave-one-scenario-out** needs all six variants present as separate scenario tags,
   which the naming convention in §12.2 already gives you for free.

Simulate a topology or mobility variation as well if you intend to answer the
single-topology limitation (§11.4): vary it per run, keep it in the filename, and the
scenario grouping will carry it through.

---

Note: One thing still on you: the EVT regex encodes the printf format I proposed in §12.3. Your firmware isn't in this repo, so that regex is a guess at your log format — align it with the actual output before the first real run. The [warn] … carried the marker but did not match EVT message exists to tell you when it's wrong.

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
