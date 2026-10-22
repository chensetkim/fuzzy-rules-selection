# Appendix A. Data-Driven Selection of the FERMAD Fuzzy Rule Base (CARS)

> **Draft note: remove before submission.**
> - Values marked † are *provisional*. They come from a preliminary method: a seed base injected
>   into the pool and initial population, a 29-rule cap, High 60–90, one search seed, and
>   floating-point evaluation.
> - They illustrate the reporting format only. They cannot validate the revised procedure, and
>   each must be replaced with the re-run value.
> - [TBD] marks items with no preliminary value. Find all of them with `grep -n "†\|TBD"`.
> - 2026-10-22: the procedure uses no hand-crafted rules at all (no seed base in the pool or
>   the initial population, and no hand-crafted baseline), High is 0 at 50 → 100 at 80, and
>   the rule cap is 35. Every † value predates this and was produced with a seed base injected.
> - The feature descriptions in Table A.1 come from the code comments. Check them against the
>   definitions in the main text.

This appendix specifies CARS, the offline procedure that selects the rule base deployed in
FERMAD. It has three aims:

- to describe the procedure in enough detail to be reproduced (A.1–A.4);
- to justify each design decision (A.5);
- to report the evidence that the procedure and the deployed rule base generalise (A.6).

Two kinds of evidence are kept separate. Protocols P1–P3 test whether the *procedure*
generalises, by re-running it on training partitions and testing on held-out ones. Protocol P4
tests the *deployed rule base itself*, on data generated after every development decision was
frozen.

**No hand-crafted rules.** CARS is purely data-driven. The candidate pool is generated from
the training data alone and the search starts from random subsets (A.3–A.4); no hand-crafted
rule base is used, either as a prior or as a baseline.

**Deployed base.** The deployed rule base is the solution CARS selects on the full development
corpus, subject to the capacity cap in A.4 **[TBD: the code has no full-corpus run yet; it runs
P1–P3 only]**. It is compiled into the firmware without modification.

**Remaining design choices.** The authors fixed the following inputs:

- the membership functions and detection threshold, inherited from the existing firmware;
- the pruning parameters;
- the objective weights;
- the rule-count bounds.

All of these were fixed before evaluation, and none was tuned on any test partition.
Table A.6 lists every setting.

## A.1 Inference model and arithmetic

### A.1.1 Evidence features

Each detection event concerns one observed neighbour. It yields an integer evidence vector
$\mathbf{x}=(v_1,\dots,v_7)\in\{0,\dots,100\}^7$, where each feature is normalised to a
percentage scale on the node (Table A.1). Six features are *inculpatory*: a high value
indicates anomalous rank behaviour. One feature, $v_6$, is *exculpatory*: a high value offers a
benign explanation, namely node mobility.

**Table A.1.** Evidence features **[TBD: align names with the main text]**.

| Feature | Evidence | Role |
|---|---|---|
| $v_1$ | Rank monotonicity violation | inculpatory |
| $v_2$ | Trickle timer resets | inculpatory |
| $v_3$ | CUSUM rank drift / spike | inculpatory |
| $v_4$ | Rank jump relative to link cost | inculpatory |
| $v_5$ | Residual sign-flip count | inculpatory |
| $v_6$ | Mobility index | exculpatory |
| $v_7$ | Two-hop rank residual (forgery corroboration) | inculpatory |

### A.1.2 Membership functions and rules

Each feature has three linguistic terms, Low, Medium and High. Their piecewise-linear
membership functions take integer values on $0$–$100$:

$$
\mu_L(v)=\begin{cases}100 & v\le20\\ \lfloor 100(50-v)/30\rfloor & 20<v<50\\ 0 & v\ge50\end{cases}
\qquad
\mu_M(v)=\begin{cases}0 & v\le20 \text{ or } v\ge80\\ \lfloor 100(v-20)/30\rfloor & 20<v\le50\\ \lfloor 100(80-v)/30\rfloor & 50<v<80\end{cases}
$$

$$
\mu_H(v)=\begin{cases}0 & v\le50\\ \lfloor 100(v-50)/30\rfloor & 50<v<80\\ 100 & v\ge80\end{cases}
$$

Low is 100 on $[0,20]$ and decays linearly to 0 at 50; Medium is a triangle with feet at 20 and
80 and its peak at 50; High rises linearly from 0 at 50 to 100 at 80 and is saturated on
$[80,100]$. Before truncation the three sets form a strong (Ruspini) partition [6]: L and M sum
to 100 on $[20,50]$, M and H on $[50,80]$.

A rule $r$ has an antecedent $A_r\in\{\ast,L,M,H\}^7$, where $\ast$ means the feature is not
used, and a consequent $z_r\in Z=\{0,25,50,75,100\}$, read as Very Low … Very High confidence
of attack. A rule base $S$ is a set of such rules.

### A.1.3 Inference

The firing strength of a rule is the minimum membership over the features it uses:

$$
w_r=\min_{i:\,A_r[i]\neq\ast}\mu_{A_r[i]}(v_i)\in\{0,\dots,100\}.
$$

Unused features are skipped, so a two-feature rule is not penalised by the other five. The
attack confidence is the zero-order Takagi–Sugeno weighted average [7], computed with 32-bit
integer accumulators:

$$
AC=\left\lfloor\frac{\sum_{r\in S}w_r z_r}{1+\sum_{r\in S}w_r}\right\rfloor .
$$

The constant 1 is added to every denominator. An event is flagged when $AC\ge\tau=65$. When no
rule fires, $AC=0$ and the event is classified as benign (*default-to-benign*).

**Worked example.** Take a base of three rules:

- $r_a$: $v_2$ is M → 100;
- $r_b$: $v_3$ is H ∧ $v_6$ is M → 75;
- $r_c$: $v_3$ is H ∧ $v_6$ is L → 75.

For an event with $v_2=40$, $v_3=85$ and $v_6=30$, the memberships are
$\mu_M(40)=66$, $\mu_H(85)=100$, $\mu_M(30)=33$ and $\mu_L(30)=66$. The firing strengths are
therefore $w_a=66$, $w_b=\min(100,33)=33$ and $w_c=\min(100,66)=66$. This gives

$$
AC=\lfloor(66\cdot100+33\cdot75+66\cdot75)/(1+66+33+66)\rfloor=\lfloor14025/166\rfloor=84,
$$

so the event is flagged. For an event with $v_2=v_3=10$, no rule fires and $AC=0$.

**One arithmetic throughout.** All fitness evaluations and all reported metrics use an exact
integer re-implementation of this firmware arithmetic. Floating-point inference is not used at
any stage, so a rule base is scored offline exactly as it will run on the mote. As a check,
the re-implementation was compared with the firmware's own membership and inference
functions compiled from its C source: it produced the identical $AC$ on all 40,000 test
cases (200 random rule bases × 200 random evidence vectors). It reproduces the firmware's
logged $AC$ values on **[TBD]%** of simulated events **[TBD: requires the rule base that was
deployed when the corpus was recorded]**.

## A.2 Data and labelling

**Development corpus.** The development corpus contains 390,201 detection events, 21.9% of
them attacks (after the exclusions below). It comes from Cooja simulations of RPL networks under six rank-attack variants:

| Variant | Attack behaviour |
|---|---|
| S1 | decreased rank, abrupt jump |
| S2 | decreased rank, slow drift |
| S3 | increased rank, abrupt jump |
| S4 | increased rank, slow drift |
| S5 | rank fluctuation |
| S6 | forged two-hop rank |

Each variant is simulated in static and mobile deployments, with 3, 6 and 9 attackers, and
with three executions per configuration.

- The static simulation is deterministic: its three executions are byte-identical, so one is
  used.
- The mobile executions differ in their random mobility realisation.
- All variants share the same topology and mobility model. Their pre-attack event streams
  differ, so the variants are not replays of a common trace.

**Independent evaluation corpus (P4).** A second corpus of **[TBD: size]** events was
generated *after* all CARS settings and the deployed base were frozen. It uses new
simulation seeds **[TBD: and a different topology/mobility trace]**. It was used for nothing
except the P4 evaluation in A.6.

**Labelling target.** The target is *current malicious behaviour*. Each attacker's attack phase
starts at its own launch time $t_a(j)$, which the attacker mote logs when its attack starts
(one launch record per attacker; 200.4–331.0 s of simulated time across the 432 attackers). An
event is labelled malicious ($y=1$) when the observed node $j$ is an attacker and
$t\ge t_a(j)$; all other retained events are labelled benign ($y=0$).

Two kinds of event are removed rather than labelled:

- Events *reported by* attacker nodes. Attackers do not run the IDS honestly, so their reports
  are not evidence the deployed system would act on.
- The 7,714 observations *of* attackers before their launch. Before launch an attacker behaves
  honestly, so either label would put noise into a region the rules cannot separate.

## A.3 Candidate pool

In P1–P3, every step in A.3 and A.4 uses only the training partition of the protocol or fold
concerned. Algorithm A.1 summarises the whole procedure.

**Algorithm A.1.** CARS.

```
Input : training events D, settings Θ (Table A.6)
Output: selected rule base S*

 1  (X, n) ← distinct (evidence vector, label) pairs of D, n = event counts
 2  P ← WangMendelCells(X, n, 200) ∪ Enumerate(max_terms = 4)
 3  for each r in P:
 4      c_r, s_r, z_r ← confidence, support, consequent of r on D  (count-weighted, integer arithmetic)
 5  P ← { r ∈ P : s_r ≥ s_min  and  |c_r − 0.5| ≥ m }
 6  W ← firing strengths of every r ∈ P on every row of X (computed once)
 7  (W and n are reused for every fitness evaluation)
 8  Pop_0 ← sparse random subsets
 9  Front ← NSGA-II(Pop_0; objectives (1−F1, FPR, |S|/U); 12 ≤ |S| ≤ U)
10  S* ← argmin over Front of weighted, min–max-normalised training objectives
11  return S*                                   (exported as integer C for the firmware)
```

**Weighted rows** (line 1). The inference depends only on the evidence vector, and about 10% of
events have a distinct one. All of A.3 and A.4 therefore works on the distinct (vector, label)
pairs of the **whole** training partition, each weighted by its event count $n$; every count
below (confidence, support, cell occupancy, $F_1$, FPR) is weighted, so the result is exactly
the one on the individual events. This reduces the P1 training partition from 273,138 events to
31,138 rows. Reported test metrics always use the full test partition.

**Generated candidates** (line 2). Two generators produce the pool:

- *Wang–Mendel-style cell rules* [1]. Each training event is assigned to the grid cell of its
  strongest term per feature, and the 200 most frequent cells become seven-term antecedents.
  This differs from the original method in two ways: occupancy, not rule degree, ranks the
  cells; and conflicts are resolved by the consequent step below.
- *Bounded enumeration.* Every antecedent with one to four features is generated:
  $\sum_{k=1}^{4}\binom{7}{k}3^k=3{,}990$ candidates.

Enumerated rules use at most four features, so the two sets cannot overlap.

**Consequents** (lines 3–4). For each candidate we compute its confidence and
support [2] over the training events $D$:

$$
c_r=\frac{\sum_{\mathbf{x}\in D:\,y=1}w_r(\mathbf{x})}{\sum_{\mathbf{x}\in D}w_r(\mathbf{x})},\qquad
s_r=\frac{1}{100\,|D|}\sum_{\mathbf{x}\in D}w_r(\mathbf{x}).
$$

$c_r$ is the firing-weighted fraction of attacks among the events the rule covers. $s_r$ is its
mean firing strength on a $[0,1]$ scale. The consequent is $z_r=\arg\min_{z\in Z}|100c_r-z|$,
with ties resolved toward the smaller $z$.

**Pruning** (line 5). A candidate is kept if both conditions hold:

- $s_r\ge s_{\min}=0.005$. A rule that almost never fires cannot influence $AC$, but it still
  enlarges the search space.
- $|c_r-0.5|\ge m=0.15$. A rule whose confidence is close to 0.5 fires about equally on
  attack and benign events, and would only dilute the weighted average. A kept rule has
  $c_r\le0.35$ or $c_r\ge0.65$, so no kept rule receives $z=50$.

The margin is measured from 0.5, not from the training attack prior $\pi\approx0.21$. A
rule whose confidence equals the prior therefore counts as benign evidence (it is kept when
$c_r\le0.35$); a prior-centred margin is evaluated as an ablation (Table A.5).

**Generated rules only.** Every rule in the pool is generated from the training partition,
with a data-assigned consequent. Each antecedent appears in the pool once. The pool contains
**[TBD]** candidates across splits.

## A.4 Multi-objective subset selection

**Encoding.** A binary chromosome $\mathbf{b}\in\{0,1\}^{|P|}$ marks which candidates form the
rule base $S$ [2, 3]. With $|P|$ in the hundreds, the search space of $2^{|P|}$ subsets rules
out exhaustive search.

**Objectives and constraints** (line 9). NSGA-II [4] minimises three objectives on the
training partition:

$$
f_1=1-F_1,\qquad f_2=\mathrm{FPR},\qquad f_3=|S|/U,
$$

subject to $12\le|S|\le U$. Infeasible subsets are handled by constraint domination:
feasible subsets dominate infeasible ones, and infeasible subsets are ranked by their
constraint violation.

**Rule-count bounds.**

- *Upper bound.* $U=35$, the rule budget assumed to fit the FERMAD firmware on the Zolertia
  Z1 (MSP430F2617: 8 KB RAM, 92 KB flash). It is an implementation limit, not a measured
  maximum capacity **[TBD: confirm that 35 rules fit the firmware's rule allocation]**.
- *Rule count as a memory proxy.* Rule count is only a proxy for memory cost. During inference
  each rule needs a 16-bit firing strength and an 8-bit consequent, but its flash cost grows
  with antecedent length. We therefore report measured values for the deployed base:
  full-image RAM and flash usage **[TBD]**, worst-case stack of the inference routine **[TBD]**,
  and flash cost per rule as a function of antecedent length **[TBD]**.
- *Lower bound.* The bound of 12 is a heuristic intended to discourage degenerate bases. It
  does not guarantee coverage, so coverage is measured directly (A.6).

**Search settings.**

- Population 150 and 250 generations, i.e. 37,500 fitness evaluations per run.
- Uniform crossover ($p=0.9$) and bit-flip mutation with probability $1/|P|$ per bit.
- Duplicate elimination.

**Computational cost** (lines 6–7). The firing strengths of all candidates on the weighted rows
are computed once. Each evaluation then reduces to a masked weighted sum over about 31,000 rows,
which keeps a run tractable. A single run takes **[TBD]** minutes on **[TBD: hardware]**.

**Initial population** (line 8). Every individual is a sparse random subset with about 2% of
candidates switched on. No prior rule base is seeded.

**Choosing one solution** (line 10). From the final front we select the solution that minimises
the weighted sum of min–max-normalised training objectives, with weights $(0.6,0.3,0.1)$ for
$(f_1,f_2,f_3)$. An objective that is constant across the front contributes zero. This is a
preference-weighted choice, not a geometric knee point [8]. Test data are never used.

**Deployed base.** The deployed base is produced by running Algorithm A.1 on the full
development corpus with seed 42† **[TBD: not yet implemented in the code]**. Its size is whatever that run selects, within
$12\le|S|\le35$. The base is exported automatically as integer C code in the form of A.1.3,
with no manual transcription. It is listed in Table A.4 and released as a machine-readable file
with the code **[TBD: link]**.

## A.5 Design rationale

Table A.2 gives the reason for each design decision and the prior work it follows.

**Table A.2.** Design decisions.

| Decision | Reason | Ref. |
|---|---|---|
| Wang–Mendel-style cells | Anchor the pool in regions of input space the data occupies | [1] |
| Enumeration of ≤4-term antecedents | Keep short, auditable rules reachable; Wang–Mendel rules always use all seven features | [2, 6] |
| Certainty-grade consequents | Standard consequent assignment for fuzzy classification rules | [2, 3] |
| Prior-relative confidence margin | Remove rules that are no more predictive than the base rate | — |
| Binary subset encoding + NSGA-II | Canonical formulation of fuzzy rule selection; elitist, no niching parameter to tune | [3, 4] |
| FPR as its own objective | At deployment prevalence false alarms dominate operating cost; $F_1$ on a balanced-ish test set understates this | [5] |
| Rule count as an objective | Pressure toward compact bases inside the cap; size is a primary interpretability measure | [3, 6] |
| Random initial population, no prior rule base | The selection depends on the data alone; seeding a prior rule base is the usual way to inject expert knowledge in genetic fuzzy systems [9], and is deliberately not used | [9] |
| Fixed membership functions | Tuning breakpoints and rules on the same data would re-introduce circularity one level down | — |
| Integer evaluation | Removes any mismatch between the evaluated and the deployed arithmetic | — |
| Splits by execution and by variant | Row-level random splits leak correlated events across the split | [10] |

## A.6 Validation

### A.6.1 Protocols

P1–P3 validate the *procedure*. Each re-runs Algorithm A.1 on its own training partition with
$R=$ **[TBD, ≥5]** search seeds:

- **P1, stratified hold-out.** A 70/30 split of *events* within each scenario. Events from one
  execution fall on both sides of the split, so P1 is an optimistic reference, retained only
  for comparison with common practice.
- **P2, execution hold-out.** Training uses mobile executions 1–2 plus the static execution.
  Testing uses mobile execution 3, a mobility realisation never seen during selection.
- **P3, leave-one-scenario-out.** Six folds, each holding out every execution of one attack
  variant. Because the variants share topology and mobility model, P3 measures transfer across
  attack variants, not across networks.

P4 validates the *deployed rule base* itself. That base is evaluated unchanged on the
independent corpus (A.2). No selection is run on P4 data.

### A.6.2 Reporting

**Statistical unit.** Search seeds re-use the same test observations, so they measure
optimisation variability, not additional independent evidence. We therefore report two
levels:

- *Within each fold:* the median and range over seeds (Supplementary Table S1).
- *Across folds:* the mean and s.d. of the per-fold medians.

**Data ceiling.** Identical evidence vectors occur with both labels, so no classifier of
$v_1..v_7$ can be perfect. For each test partition we report the $F_1$ of predicting every
distinct vector as its majority label in that partition, an upper bound for any rule base
(about 0.988 for P1 and P2). A result at or near it would indicate leakage rather than a better
rule base.

**Coverage.** Coverage is reported separately by class:

- $\mathrm{NF}_1=P(\text{no rule fires}\mid y=1)$ is the share of attacks missed through zero
  coverage.
- $\mathrm{NF}_0=P(\text{no rule fires}\mid y=0)$ is the share of benign events classified
  benign by default.

These rates describe *how* decisions arise; a low FPR obtained through a high NF$_0$ is
benign-by-default, not discrimination.

**Precision.** Precision is measured at the tested attack prevalence of 15–28%. It does not
establish the false-alarm burden at deployment prevalence, which is expected to be lower.

### A.6.3 Results

**Table A.3.** Test results at $\tau=65$: across-fold mean ± s.d. of per-fold seed medians.

| Protocol | Rules | CARS P / R / $F_1$ | CARS FPR | CARS NF$_1$ / NF$_0$ |
|---|---|---|---|---|
| P1 | 15† | .975 / .863 / .915† | .0061† | 1.3% / 24.4%† |
| P2 | 15† | .977 / .724 / .832† | .0038† | 0.0% / 8.4%† |
| P3 (6 folds) | 12–19† | .965 / .760 / .836 ± .131† | .0064 ± .0015† | 7.7% / 30.9%† |
| P4 (deployed base) | [TBD] | [TBD] | [TBD] | [TBD] |

**Reading the preliminary figures.** These † values come from the preliminary method, and
three points about them carry over to the revised analysis:

1. *False alarms.* FPR stayed below 1% in every protocol and every P3 fold (at most 0.82%†).
2. *Detection.* $F_1$ was high in P1 and P2 (.915, .832) but uneven across the P3 folds. The
   spread over P3 folds (s.d. 0.13) shows that transfer to an unseen attack variant is uneven.
3. *Coverage.* The preliminary bases left a large share of benign events with no firing rule,
   with NF$_0$ up to 89.5% in fold S2†. That fraction of the low FPR arises by default, not by
   discrimination.

The revised procedure is judged on the same measures.

**Table A.4.** Deployed rule base (antecedent → $z$; features not listed are $\ast$).

- "Avail." is the fraction of validation runs in which the antecedent–consequent pair was in
  the pool.
- "Sel." is the fraction of those runs in which the pair was selected.

| # | Antecedent | $z$ | Avail. | Sel. |
|---|---|---|---|---|
| 1 | $v_5L \wedge v_6M$ | 25† | [TBD] | [TBD] |
| 2 | $v_3H \wedge v_6M$ | 75† | [TBD] | [TBD] |
| 3 | $v_2M$ | 100† | [TBD] | [TBD] |
| 4 | $v_2M \wedge v_4H \wedge v_5L \wedge v_7L$ | 100† | [TBD] | [TBD] |
| 5 | $v_2M \wedge v_3H$ | 100† | [TBD] | [TBD] |
| 6 | $v_2H \wedge v_4M \wedge v_5L \wedge v_6M$ | 75† | [TBD] | [TBD] |
| 7 | $v_2H \wedge v_3H \wedge v_5L \wedge v_6L$ | 100† | [TBD] | [TBD] |
| 8 | $v_2H \wedge v_3H \wedge v_4M \wedge v_6M$ | 75† | [TBD] | [TBD] |
| 9 | $v_1L \wedge v_5M$ | 100† | [TBD] | [TBD] |
| 10 | $v_1L \wedge v_2H \wedge v_7L$ | 100† | [TBD] | [TBD] |
| 11 | $v_1H \wedge v_3H \wedge v_6M$ | 75† | [TBD] | [TBD] |
| 12 | $v_1H \wedge v_3H \wedge v_4L \wedge v_6M$ | 75† | [TBD] | [TBD] |
| 13 | $v_1H \wedge v_2H \wedge v_4H \wedge v_5L$ | 100† | [TBD] | [TBD] |
| 14 | $v_1H \wedge v_2H \wedge v_3H \wedge v_4L \wedge v_5L \wedge v_6M \wedge v_7L$ | 75† | [TBD] | [TBD] |
| 15 | $v_3H \wedge v_6L$ | 75† | [TBD] | [TBD] |

*† Provisional: this is the 15-rule base from the preliminary P1 run (made with the earlier,
seeded procedure; #15 was a seed rule). It is replaced by the deployed base from the
full-corpus run, in which every rule is generated from data.*

**Interpretation of the rules.** The preliminary base illustrates how a selected base reads:

- Trickle resets at Medium or High ($v_2$) are the most frequent attack indicator.
- High CUSUM drift ($v_3$) combined with a mobility condition ($v_6$) yields High confidence.
- A single broad rule (#1) maps low sign-flip activity with moderate mobility to Low confidence.

**Interpretation of selection frequency.** Selection frequency measures how *stable* a rule is
under the specified procedure. It does not show that an individual rule is necessary or
independently correct. A candidate may be pruned, or change consequent, across folds; "Avail."
accounts for this.

**Table A.5.** Ablations under P2, P3 and P4 (seed medians).

| Variant | P2 $F_1$ / FPR | P3 $F_1$ / FPR | P4 $F_1$ / FPR | NF$_1$ / NF$_0$ |
|---|---|---|---|---|
| CARS (as specified) | [TBD] | [TBD] | [TBD] | [TBD] |
| Prior-centred confidence margin ($\lvert c_r-\pi\rvert\ge m$) | [TBD] | [TBD] | [TBD] | [TBD] |
| Pre-launch attacker events labelled benign instead of removed | [TBD] | [TBD] | [TBD] | [TBD] |
| Fixed attack start $t_a=300$ s for every attacker instead of its own launch time | [TBD] | [TBD] | [TBD] | [TBD] |
| Floating-point instead of integer evaluation | [TBD] | [TBD] | [TBD] | [TBD] |

## A.7 Reproducibility

**Table A.6.** Complete settings.

| Setting | Value |
|---|---|
| Membership functions | L: (20, 50); M: (20, 50, 80); H: (50, 80), integer scale 0–100 |
| Consequent set $Z$ | {0, 25, 50, 75, 100} |
| Detection threshold $\tau$ | 65 |
| Enumeration bound | ≤ 4 antecedent terms |
| Wang–Mendel cells | 200 most frequent |
| Labelling | $y=1$ iff observed node $j$ is an attacker and $t\ge t_a(j)$, its own launch time; attacker-reported events and pre-launch attacker events removed |
| Pruning | $s_{\min}=0.005$; $\lvert c_r-0.5\rvert\ge m=0.15$ |
| Rule bounds | $12\le\lvert S\rvert\le35$ |
| NSGA-II | pop 150, 250 generations, uniform crossover 0.9, bit-flip $1/\lvert P\rvert$, duplicate elimination |
| Initial population | random subsets at ≈2% density (no seed base) |
| Training data | the whole training partition, as distinct (vector, label) rows weighted by event count; used for pool generation, consequents, pruning and fitness |
| Solution choice | weights (0.6, 0.3, 0.1) on min–max-normalised $(f_1,f_2,f_3)$ |
| Search seeds | $R=$ **[TBD, ≥5]**; deployment run seed 42† |
| Split seed (P1) | 42 |

The code, the deployed base, and the scripts that regenerate every table
are available at **[TBD: link]**. The simulation configurations and event logs are available
at **[TBD: link / on request]**.

## A.8 Limitations

- **Simulation scope.** Labels come from simulation ground truth, and the number of independent
  executions is small. Results may not transfer to other topologies, radio conditions or
  traffic patterns.
- **No external reference base.** Results are reported in absolute terms; the appendix does not
  compare against a hand-crafted rule base.
- **Design choices.** The membership functions, threshold, objective weights and bounds are
  choices made by the authors. CARS selects rules conditional on them; it does not optimise
  them. Performance at other thresholds is not reported.
- **Rule-level evidence.** Selection frequency shows stability, not necessity.
- **Deployment prevalence.** All metrics are measured at an attack prevalence far above what a
  real network would typically see.

## References

[1] L.-X. Wang and J. M. Mendel, "Generating fuzzy rules by learning from examples," *IEEE Trans. Syst., Man, Cybern.*, vol. 22, no. 6, pp. 1414–1427, 1992.
[2] H. Ishibuchi, T. Murata, and I. B. Türkşen, "Single-objective and two-objective genetic algorithms for selecting linguistic rules for pattern classification problems," *Fuzzy Sets Syst.*, vol. 89, no. 2, pp. 135–149, 1997.
[3] H. Ishibuchi and T. Yamamoto, "Fuzzy rule selection by multi-objective genetic local search algorithms and rule evaluation measures in data mining," *Fuzzy Sets Syst.*, vol. 141, no. 1, pp. 59–88, 2004.
[4] K. Deb, A. Pratap, S. Agarwal, and T. Meyarivan, "A fast and elitist multiobjective genetic algorithm: NSGA-II," *IEEE Trans. Evol. Comput.*, vol. 6, no. 2, pp. 182–197, 2002.
[5] S. Axelsson, "The base-rate fallacy and the difficulty of intrusion detection," *ACM Trans. Inf. Syst. Secur.*, vol. 3, no. 3, pp. 186–205, 2000.
[6] M. J. Gacto, R. Alcalá, and F. Herrera, "Interpretability of linguistic fuzzy rule-based systems: An overview of interpretability measures," *Inf. Sci.*, vol. 181, no. 20, pp. 4340–4360, 2011.
[7] T. Takagi and M. Sugeno, "Fuzzy identification of systems and its applications to modeling and control," *IEEE Trans. Syst., Man, Cybern.*, vol. 15, no. 1, pp. 116–132, 1985.
[8] J. Branke, K. Deb, H. Dierolf, and M. Osswald, "Finding knees in multi-objective optimization," in *Proc. PPSN VIII*, LNCS 3242, pp. 722–731, 2004.
[9] O. Cordón, F. Herrera, F. Hoffmann, and L. Magdalena, *Genetic Fuzzy Systems: Evolutionary Tuning and Learning of Fuzzy Knowledge Bases*. World Scientific, 2001.
[10] D. Arp et al., "Dos and don'ts of machine learning in computer security," in *Proc. 31st USENIX Security Symp.*, 2022.
