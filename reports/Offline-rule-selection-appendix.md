# Appendix A. Data-Driven Selection of the EF-RMAD Fuzzy Rule Base (CARS)

> **Draft note: remove before submission.**
> - Values marked † are *provisional*. They come from a preliminary method: a different seed
>   base, a 29-rule cap, one search seed, a 0.5-centred margin, pre-activation events
>   excluded, and floating-point evaluation.
> - They illustrate the reporting format only. They cannot validate the revised procedure, and
>   each must be replaced with the re-run value.
> - [TBD] marks items with no preliminary value. Find all of them with `grep -n "†\|TBD"`.
> - The feature descriptions in Table A.1 come from the code comments. Check them against the
>   definitions in the main text.

This appendix specifies CARS, the offline procedure that selects the rule base deployed in
EF-RMAD. It has three aims:

- to describe the procedure in enough detail to be reproduced (A.1–A.4);
- to justify each design decision (A.5);
- to report the evidence that the procedure and the deployed rule base generalise (A.6).

Two kinds of evidence are kept separate. Protocols P1–P3 test whether the *procedure*
generalises, by re-running it on training partitions and testing on held-out ones. Protocol P4
tests the *deployed rule base itself*, on data generated after every development decision was
frozen.

**Seed base.** During the development of EF-RMAD, the authors assembled an initial rule base
$K_0$ of 33 rules from three sources: domain analysis of the attack taxonomy, preliminary
selection runs, and analysis of simulation traces. Its data provenance is given in A.3.

CARS uses $K_0$ as a prior. Seed rules receive preferential inclusion and initialization,
as detailed in A.3–A.4. All candidate subsets are then evaluated under the same objectives.

**Deployed base.** The deployed rule base is the solution CARS selects on the full development
corpus, subject to the capacity cap in A.4. It is compiled into the firmware without
modification.

**Remaining design choices.** The authors fixed the following inputs:

- the membership functions and detection threshold, inherited from the existing firmware;
- the pruning parameters;
- the objective weights;
- the rule-count bounds;
- the seed base $K_0$.

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
\mu_H(v)=\begin{cases}0 & v\le60\\ \lfloor 100(v-60)/30\rfloor & 60<v<90\\ 100 & v\ge90\end{cases}
$$

The High set starts at 60, not 50, which leaves a gap on $(50,60]$ where only Medium is
non-zero. The gap is deliberate: it suppresses High firings on moderately elevated evidence.
As a consequence, the three sets do not form a strong (Ruspini) partition [6].

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
$\mu_M(40)=66$, $\mu_H(85)=83$, $\mu_M(30)=33$ and $\mu_L(30)=66$. The firing strengths are
therefore $w_a=66$, $w_b=\min(83,33)=33$ and $w_c=\min(83,66)=66$. This gives

$$
AC=\lfloor(66\cdot100+33\cdot75+66\cdot75)/(1+66+33+66)\rfloor=\lfloor14025/166\rfloor=84,
$$

so the event is flagged. For an event with $v_2=v_3=10$, no rule fires and $AC=0$.

**One arithmetic throughout.** All fitness evaluations and all reported metrics use an exact
integer re-implementation of this firmware arithmetic. Floating-point inference is not used at
any stage, so a rule base is scored offline exactly as it will run on the mote. As a check,
the re-implementation reproduces the firmware's logged $AC$ values on **[TBD]%** of simulated
events.

## A.2 Data and labelling

**Development corpus.** The development corpus contains 397,915 detection events, 21.1% of
them attacks. It comes from Cooja simulations of RPL networks under six rank-attack variants:

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
generated *after* $K_0$, all CARS settings and the deployed base were frozen. It uses new
simulation seeds **[TBD: and a different topology/mobility trace]**. It was used for nothing
except the P4 evaluation in A.6.

**Labelling target.** The target is *current malicious behaviour*. An event is labelled
malicious ($y=1$) when the observed node is an attacker and the event occurs after that
attacker's activation. All other events are labelled benign ($y=0$). This includes the 9,577
pre-activation observations of attackers, because those nodes behave honestly at that point:
labelling them benign matches what the detector should output.

Events *reported by* attacker nodes are removed. Attackers do not run the IDS honestly, so
their reports are not evidence the deployed system would act on.

## A.3 Candidate pool

In P1–P3, every step in A.3 and A.4 uses only the training partition of the protocol or fold
concerned. Algorithm A.1 summarises the whole procedure.

**Algorithm A.1.** CARS.

```
Input : training events D, seed base K0, settings Θ (Table A.6)
Output: selected rule base S*

 1  P_gen ← WangMendelCells(D, 200) ∪ Enumerate(max_terms = 4)
 2  for each r in P_gen:
 3      c_r, s_r ← confidence and support of r on D          (integer arithmetic)
 4      z_r      ← nearest element of Z to 100·c_r            (ties → smaller)
 5  P_gen ← { r ∈ P_gen : s_r ≥ s_min  and  |c_r − π| ≥ m }
 6  P ← { r ∈ P_gen : A_r not an antecedent of K0 } ∪ K0      (K0 keeps its consequents)
 7  D_s ← stratified sample of D (40,000 events)
 8  W ← firing strengths of every r ∈ P on every event in D_s (computed once)
 9  Pop_0 ← { K0 } ∪ { 9 three-bit perturbations of K0 } ∪ { sparse random subsets }
10  Front ← NSGA-II(Pop_0; objectives (1−F1, FPR, |S|/U); 12 ≤ |S| ≤ U)
11  S* ← argmin over Front of weighted, min–max-normalised training objectives
12  return S*                                   (exported as integer C for the firmware)
```

**Generated candidates** (line 1). Two generators produce the generated part of the pool:

- *Wang–Mendel-style cell rules* [1]. Each training event is assigned to the grid cell of its
  strongest term per feature, and the 200 most frequent cells become seven-term antecedents.
  This differs from the original method in two ways: occupancy, not rule degree, ranks the
  cells; and conflicts are resolved by the consequent step below.
- *Bounded enumeration.* Every antecedent with one to four features is generated:
  $\sum_{k=1}^{4}\binom{7}{k}3^k=3{,}990$ candidates.

Enumerated rules use at most four features, so the two sets cannot overlap.

**Consequents** (lines 2–4). For each generated candidate we compute its confidence and
support [2], pooled over all training events:

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
- $|c_r-\pi|\ge m=0.15$†, where $\pi$ is the training attack prior. A rule whose confidence is
  close to the prior is no more predictive than the base rate, and would only dilute the
  weighted average.

The margin is measured from $\pi$, not from 0.5. At $\pi\approx0.21$, a 0.5-centred margin
would retain rules that fire uniformly on all events.

**Seed rules and their privileges** (line 6). The rules of $K_0$ enter the pool with four
privileges over generated candidates:

1. They bypass pruning; **[TBD: k]** of them would otherwise be removed.
2. They keep their stated consequents instead of data-assigned ones.
3. They replace any generated candidate with an identical antecedent.
4. They are represented in the initial population (A.4).

Each antecedent therefore appears in the pool once, with one consequent. The pool contains
654–717† candidates across splits.

**Provenance of $K_0$.** The preliminary runs and traces from which $K_0$ was developed used
**[TBD: which executions, deployments and attack variants]**. To the extent that these overlap
the test partitions of P1–P3, $K_0$ carries information from those partitions. Rebuilding the
pool inside each training partition does not remove it.

The appendix handles this in two ways:

- The *generated-only* variant (Table A.5) omits $K_0$ entirely, so it is free of this
  leakage in every fold.
- P4 evaluates the deployed base on data that did not exist when $K_0$ was developed.

P1–P3 results for the seeded procedure should be read as conditional on $K_0$.

## A.4 Multi-objective subset selection

**Encoding.** A binary chromosome $\mathbf{b}\in\{0,1\}^{|P|}$ marks which candidates form the
rule base $S$ [2, 3]. With $|P|$ in the hundreds, the search space of $2^{|P|}$ subsets rules
out exhaustive search.

**Objectives and constraints** (line 10). NSGA-II [4] minimises three objectives on the
training sample:

$$
f_1=1-F_1,\qquad f_2=\mathrm{FPR},\qquad f_3=|S|/U,
$$

subject to $12\le|S|\le U$. Infeasible subsets are handled by constraint domination:
feasible subsets dominate infeasible ones, and infeasible subsets are ranked by their
constraint violation.

**Rule-count bounds.**

- *Upper bound.* $U=33$ is the rule allocation of the current EF-RMAD firmware on the
  Zolertia Z1 (MSP430F2617: 8 KB RAM, 92 KB flash). It is an implementation limit, not a
  measured maximum capacity **[TBD: confirm]**.
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

**Fitness sample** (line 7). Fitness is evaluated on a 40,000-event training sample. It is drawn
without replacement from every stratum (scenario × deployment × attacker count × execution),
in proportion to stratum size and with at least one event per stratum.

**Computational cost** (line 8). The firing strengths of all candidates on the fitness sample are
computed once. Each evaluation then reduces to a masked weighted sum, which keeps a run
tractable. A single run takes **[TBD]** minutes on **[TBD: hardware]**.

**Seeding** (line 9). The initial population contains $K_0$, nine three-bit perturbations of
$K_0$, and sparse random subsets with about 2% of candidates switched on.

Whether a seed rule is retained depends on several factors:

- the objectives;
- this initialization;
- the stochastic search;
- NSGA-II's diversity-based truncation, which can discard non-dominated solutions;
- interactions with the other rules in a subset.

**Choosing one solution** (line 11). From the final front we select the solution that minimises
the weighted sum of min–max-normalised training objectives, with weights $(0.6,0.3,0.1)$ for
$(f_1,f_2,f_3)$. An objective that is constant across the front contributes zero. This is a
preference-weighted choice, not a geometric knee point [8]. Test data are never used.

**Deployed base.** The deployed base is produced by running Algorithm A.1 on the full
development corpus with seed 42†. Its size is whatever that run selects, within
$12\le|S|\le33$. The base is exported automatically as integer C code in the form of A.1.3,
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
| Seeded initial population | Standard way to inject prior knowledge in genetic fuzzy systems | [9] |
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

Paired differences against the unselected $K_0$ are computed per fold on the seed medians,
then aggregated the same way.

**Dominance.** For each fold we report the fraction of seeds whose selected base dominates
$K_0$ on the training objectives.

**Coverage.** Coverage is reported separately by class:

- $\mathrm{NF}_1=P(\text{no rule fires}\mid y=1)$ is the share of attacks missed through zero
  coverage.
- $\mathrm{NF}_0=P(\text{no rule fires}\mid y=0)$ is the share of benign events classified
  benign by default.

These rates describe *how* decisions arise. They do not by themselves explain differences
from the baseline.

**Precision.** Precision is measured at the tested attack prevalence of 15–28%. It does not
establish the false-alarm burden at deployment prevalence, which is expected to be lower.

### A.6.3 Results

**Table A.3.** Test results at $\tau=65$: across-fold mean ± s.d. of per-fold seed medians.

| Protocol | Rules | CARS P / R / $F_1$ | CARS FPR | CARS NF$_1$ / NF$_0$ | $K_0$ $F_1$ / FPR | $K_0$ NF$_1$ / NF$_0$ |
|---|---|---|---|---|---|---|
| P1 | 15† | .975 / .863 / .915† | .0061† | 1.3% / 24.4%† | .850 / .0461† | 6.4% / 3.2%† |
| P2 | 15† | .977 / .724 / .832† | .0038† | 0.0% / 8.4%† | .783 / .0552† | 9.7% / 3.6%† |
| P3 (6 folds) | 12–19† | .965 / .760 / .836 ± .131† | .0064 ± .0015† | 7.7% / 30.9%† | .806 ± .151 / .0472 ± .0164† | 8.3% / 3.3%† |
| P4 (deployed base) | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] |

**Reading the preliminary figures.** These † values come from the preliminary method, and
three points about them carry over to the revised analysis:

1. *False alarms.* The preliminary bases had a lower FPR than their seed base in every protocol.
2. *Detection.* $F_1$ was higher in P1 and P2, but not uniformly across the P3 folds. The
   spread over P3 folds (s.d. 0.13) shows that transfer to an unseen attack variant is uneven.
3. *Coverage.* The preliminary bases left a large share of benign events with no firing rule,
   with NF$_0$ up to 89.5% in fold S2†. That fraction of the low FPR arises by default, not by
   discrimination.

The revised procedure is judged on the same measures.

**Preliminary dominance.** Under one seed, the preliminary base dominated its seed base in
7 of 8 protocol/fold runs† (all except fold S5†).

**Table A.4.** Deployed rule base (antecedent → $z$; features not listed are $\ast$).

- "Avail." is the fraction of validation runs in which the antecedent–consequent pair was in
  the pool.
- "Sel." is the fraction of those runs in which the pair was selected.

| # | Antecedent | $z$ | Origin | Avail. | Sel. |
|---|---|---|---|---|---|
| 1 | $v_5L \wedge v_6M$ | 25† | generated† | [TBD] | [TBD] |
| 2 | $v_3H \wedge v_6M$ | 75† | generated† | [TBD] | [TBD] |
| 3 | $v_2M$ | 100† | generated† | [TBD] | [TBD] |
| 4 | $v_2M \wedge v_4H \wedge v_5L \wedge v_7L$ | 100† | generated† | [TBD] | [TBD] |
| 5 | $v_2M \wedge v_3H$ | 100† | generated† | [TBD] | [TBD] |
| 6 | $v_2H \wedge v_4M \wedge v_5L \wedge v_6M$ | 75† | generated† | [TBD] | [TBD] |
| 7 | $v_2H \wedge v_3H \wedge v_5L \wedge v_6L$ | 100† | generated† | [TBD] | [TBD] |
| 8 | $v_2H \wedge v_3H \wedge v_4M \wedge v_6M$ | 75† | generated† | [TBD] | [TBD] |
| 9 | $v_1L \wedge v_5M$ | 100† | generated† | [TBD] | [TBD] |
| 10 | $v_1L \wedge v_2H \wedge v_7L$ | 100† | generated† | [TBD] | [TBD] |
| 11 | $v_1H \wedge v_3H \wedge v_6M$ | 75† | generated† | [TBD] | [TBD] |
| 12 | $v_1H \wedge v_3H \wedge v_4L \wedge v_6M$ | 75† | generated† | [TBD] | [TBD] |
| 13 | $v_1H \wedge v_2H \wedge v_4H \wedge v_5L$ | 100† | generated† | [TBD] | [TBD] |
| 14 | $v_1H \wedge v_2H \wedge v_3H \wedge v_4L \wedge v_5L \wedge v_6M \wedge v_7L$ | 75† | generated† | [TBD] | [TBD] |
| 15 | $v_3H \wedge v_6L$ | 75† | seed† | [TBD] | [TBD] |

*† Provisional: this is the 15-rule base from the preliminary P1 run. It is replaced by the
deployed base from the full-corpus run.*

**Interpretation of the rules.** The preliminary base illustrates how a selected base reads:

- Trickle resets at Medium or High ($v_2$) are the most frequent attack indicator.
- High CUSUM drift ($v_3$) combined with a mobility condition ($v_6$) yields High confidence.
- A single broad rule (#1) maps low sign-flip activity with moderate mobility to Low confidence.

**Interpretation of selection frequency.** Selection frequency measures how *stable* a rule is
under the specified procedure. It does not show that an individual rule is necessary or
independently correct. Seed rules are always available, whereas generated candidates may be
pruned or change consequent across folds, so the two kinds of rule are not directly
comparable.

**Table A.5.** Ablations under P2, P3 and P4 (seed medians).

| Variant | P2 $F_1$ / FPR | P3 $F_1$ / FPR | P4 $F_1$ / FPR | NF$_1$ / NF$_0$ |
|---|---|---|---|---|
| CARS (as specified) | .832 / .0038† | .836 / .0064† | [TBD] | [TBD] |
| Random initialization (same pool, $K_0$ not seeded) | [TBD] | [TBD] | [TBD] | [TBD] |
| Generated candidates only ($K_0$ and its privileges removed) | [TBD] | [TBD] | [TBD] | [TBD] |
| $K_0$ subject to pruning and data-assigned consequents | [TBD] | [TBD] | [TBD] | [TBD] |
| 0.5-centred confidence margin | [TBD] | [TBD] | [TBD] | [TBD] |
| Pre-activation events excluded | [TBD] | [TBD] | [TBD] | [TBD] |

Of these variants, only the generated-only one measures performance without the seed-rule prior.

## A.7 Reproducibility

**Table A.6.** Complete settings.

| Setting | Value |
|---|---|
| Membership functions | L: (20, 50); M: (20, 50, 80); H: (60, 90), integer scale 0–100 |
| Consequent set $Z$ | {0, 25, 50, 75, 100} |
| Detection threshold $\tau$ | 65 |
| Enumeration bound | ≤ 4 antecedent terms |
| Wang–Mendel cells | 200 most frequent |
| Pruning | $s_{\min}=0.005$; $m=0.15$† (margin from prior $\pi$) |
| Rule bounds | $12\le\lvert S\rvert\le33$ |
| NSGA-II | pop 150, 250 generations, uniform crossover 0.9, bit-flip $1/\lvert P\rvert$, duplicate elimination |
| Initial population | $K_0$, 9 three-bit perturbations, random subsets at ≈2% density |
| Fitness sample | 40,000 events, stratified by scenario × deployment × attackers × execution |
| Solution choice | weights (0.6, 0.3, 0.1) on min–max-normalised $(f_1,f_2,f_3)$ |
| Search seeds | $R=$ **[TBD, ≥5]**; deployment run seed 42† |
| Split seed (P1) | 42 |

The code, the seed base $K_0$, the deployed base, and the scripts that regenerate every table
are available at **[TBD: link]**. The simulation configurations and event logs are available
at **[TBD: link / on request]**.

## A.8 Limitations

- **Simulation scope.** Labels come from simulation ground truth, and the number of independent
  executions is small. Results may not transfer to other topologies, radio conditions or
  traffic patterns.
- **Dependence on $K_0$.** P1–P3 results for the seeded procedure are conditional on $K_0$,
  whose development may overlap their test data (A.3). P4 and the generated-only ablation are
  the evidence that does not depend on this.
- **Design choices.** The membership functions, threshold, objective weights, bounds and seed
  base are choices made by the authors. CARS selects rules conditional on them; it does not
  optimise them. Performance at other thresholds is not reported.
- **Rule-level evidence.** Selection frequency shows stability, not necessity. The retention or
  absence of a seed rule does not show that it is correct or wrong.
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
