# Appendix A. Data-Driven Selection of the EF-RMAD Fuzzy Rule Base (CARS)

> **Draft note: remove before submission.**
> - Values marked † are *provisional*. They come from a preliminary method: a different seed
>   base, a 29-rule cap, one search seed, a 0.5-centred margin, pre-activation events
>   excluded, and floating-point evaluation.
> - They illustrate the reporting format only. They cannot validate the revised procedure, and
>   each must be replaced with the re-run value.
> - [TBD] marks items with no preliminary value. Find all of them with `grep -n "†\|TBD"`.

This appendix specifies CARS, the offline procedure that selects the rule base deployed in
EF-RMAD. It then separates two kinds of evidence:

- evidence that the *procedure* generalises (protocols P1–P3);
- evidence for the *deployed rule base itself*, on data never used during development (P4).

**Seed base.** During the development of EF-RMAD, the authors assembled an initial rule base
$K_0$ of 33 rules from three sources: domain analysis of the attack taxonomy, preliminary
selection runs, and analysis of simulation traces. Its data provenance is given in A.3.

CARS uses $K_0$ as a prior. Seed rules receive preferential inclusion and initialization, as
detailed in A.3–A.4. All candidate subsets are then evaluated under the same objectives.

**Deployed base.** The deployed rule base is the solution CARS selects on the full development
corpus, subject to the capacity cap in A.4. It is compiled into the firmware without
modification.

**Remaining design choices.** The authors fixed the following inputs:

- the membership functions and detection threshold, inherited from the existing firmware;
- the pruning parameters;
- the objective weights;
- the rule-count bounds (A.4);
- the seed base $K_0$.

All of these were fixed before evaluation, and none was tuned on any test partition.

## A.1 Inference model and arithmetic

**Inputs and rules.** Each detection event yields an integer evidence vector
$\mathbf{x}=(v_1,\dots,v_7)\in\{0,\dots,100\}^7$. Each feature has three linguistic terms,
Low, Medium and High, with piecewise-linear membership functions:

- $\mu_L$ equals 100 on $[0,20]$ and falls to 0 at 50;
- $\mu_M$ is triangular on $(20,50,80)$;
- $\mu_H$ rises from 0 at 60 to 100 at 90.

Each ratio is truncated by integer division, for example
$\mu_L(v)=\lfloor100(50-v)/30\rfloor$. A rule $r$ has an antecedent
$A_r\in\{\ast,L,M,H\}^7$, where $\ast$ means the feature is not used, and a consequent
$z_r\in Z=\{0,25,50,75,100\}$.

**Inference.** The firing strength of a rule is
$w_r=\min_{i:A_r[i]\neq\ast}\mu_{A_r[i]}(v_i)$. The attack confidence is

$$
AC=\left\lfloor\frac{\sum_{r\in S}w_r z_r}{1+\sum_{r\in S}w_r}\right\rfloor,
$$

computed with 32-bit accumulators. The constant 1 is added to every denominator. An event is
flagged when $AC\ge\tau=65$. When no rule fires, $AC=0$ and the event is classified as benign
(*default-to-benign*).

**One arithmetic throughout.** All fitness evaluations and all reported metrics use an exact
integer re-implementation of this firmware arithmetic. Floating-point inference is not used at
any stage. As a check, the re-implementation reproduces the firmware's logged $AC$ values on
**[TBD]%** of simulated events.

## A.2 Data and labelling

**Development corpus.** The development corpus contains 397,915 detection events, 21.1% of
them attacks. It comes from Cooja simulations with the following factors:

- six rank-attack variants (S1–S6);
- static and mobile deployments;
- 3, 6 and 9 attackers;
- three executions per configuration.

The static simulation is deterministic: its three executions are byte-identical, so one is
used. All variants share the same topology and mobility model. Their pre-attack event streams
differ, so the variants are not replays of a common trace.

**Independent evaluation corpus (P4).** A second corpus of **[TBD: size]** events was
generated *after* $K_0$, all CARS settings and the deployed base were frozen. It uses new
simulation seeds **[TBD: and a different topology/mobility trace]**. It was used for nothing
except the P4 evaluation in A.5.

**Labelling target.** The target is *current malicious behaviour*. An event is labelled
malicious when the observed node is an attacker and the event occurs after that attacker's
activation. All other events are benign. This includes the 9,577 pre-activation observations
of attackers, because those nodes behave honestly at that point. Events reported by attacker
nodes are removed, because attackers do not run the IDS honestly.

## A.3 Candidate pool

In P1–P3, all steps in A.3 and A.4 use only the training partition of the protocol or fold
concerned.

**Generated candidates.** Two generators produce the generated part of the pool:

- *Wang–Mendel-style cell rules* [1]. Each training event is assigned to the grid cell of its
  strongest term per feature, and the 200 most frequent cells become seven-term antecedents.
- *Bounded enumeration.* Every antecedent with one to four features is generated
  ($\sum_{k=1}^{4}\binom{7}{k}3^k=3{,}990$ candidates).

Enumerated rules use at most four features, so the two sets cannot overlap.

**Consequents and pruning.** For each generated candidate we compute its confidence and
support [2], pooled over all training events:

$$
c_r=\frac{\sum_{y=1}w_r}{\sum w_r},\qquad s_r=\frac{1}{100\,n}\sum w_r .
$$

- The consequent is $z_r=\arg\min_{z\in Z}|100c_r-z|$, with ties resolved toward the smaller $z$.
- A candidate is kept if $s_r\ge0.005$ and $|c_r-\pi|\ge m$, where $\pi$ is the training attack
  prior and $m=0.15$†.
- Because the margin is measured from the prior, a rule that fires uniformly on all events
  ($c_r\approx\pi$) is removed.

**Seed rules and their privileges.** The rules of $K_0$ enter the pool with four privileges
over generated candidates:

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

- The *generated-only* variant (Table A.3) omits $K_0$ entirely, so it is free of this
  leakage in every fold.
- P4 evaluates the deployed base on data that did not exist when $K_0$ was developed.

P1–P3 results for the seeded procedure should be read as conditional on $K_0$.

## A.4 Multi-objective subset selection

**Problem.** A binary chromosome $\mathbf{b}\in\{0,1\}^{|P|}$ marks which candidates form the
rule base $S$ [2, 3]. NSGA-II [4] minimises three objectives,

$$
\big(1-F_1,\ \mathrm{FPR},\ |S|/U\big),
$$

subject to $12\le|S|\le U$. Infeasible subsets are handled by constraint domination:
feasible subsets dominate infeasible ones, and infeasible subsets are ranked by their
constraint violation. FPR is kept as a separate objective because false alarms dominate
operating cost at low attack prevalence [5].

**Rule-count bounds.** $U=33$ is the rule allocation of the current EF-RMAD firmware on the
Zolertia Z1 (MSP430F2617: 8 KB RAM, 92 KB flash). It is an implementation limit, not a measured
maximum capacity **[TBD: confirm]**.

Rule count is only a proxy for memory cost, because flash cost grows with antecedent length.
We therefore report measured values for the deployed base:

- full-image RAM and flash usage, **[TBD]**;
- worst-case stack of the inference routine, **[TBD]**;
- flash cost as a function of antecedent length, **[TBD]**.

The lower bound of 12 is a heuristic intended to discourage degenerate bases. It does not
guarantee coverage, so coverage is measured directly (A.5).

**Settings.**

- Population 150 and 250 generations.
- Uniform crossover ($p=0.9$) and bit-flip mutation with probability $1/|P|$ per bit.
- Duplicate elimination.
- Fitness is evaluated on a 40,000-event training sample. It is drawn without replacement from
  every stratum (scenario × deployment × attacker count × execution), in proportion to stratum
  size and with at least one event per stratum.

**Seeding.** The initial population contains $K_0$, nine three-bit perturbations of $K_0$, and
sparse random subsets.

Whether a seed rule is retained depends on several factors:

- the objectives;
- this initialization;
- the stochastic search;
- NSGA-II's diversity-based truncation, which can discard non-dominated solutions;
- interactions with the other rules in a subset.

**Choosing one solution.** From the final front we select the solution that minimises the
weighted sum of min–max-normalised training objectives, with weights $(0.6,0.3,0.1)$. An
objective that is constant across the front contributes zero, and test data are never used.

**Deployed base.** The deployed base is produced by running A.3–A.4 on the full development
corpus with seed 42†. Its size is whatever that run selects, within $12\le|S|\le33$. It is
listed in Table A.2 and released as a machine-readable file with the code **[TBD: link]**.

## A.5 Validation

**What P1–P3 validate.** P1–P3 validate the *procedure*. Each re-runs A.3–A.4 on its own
training partition with $R=$ **[TBD, ≥5]** search seeds:

- **P1, stratified hold-out.** A 70/30 split of *events* within each scenario. Events from one
  execution fall on both sides, so P1 is an optimistic reference.
- **P2, execution hold-out.** Training uses mobile executions 1–2 plus the static execution.
  Testing uses mobile execution 3.
- **P3, leave-one-scenario-out.** Six folds, each holding out every execution of one attack
  variant. P3 measures transfer across attack variants, not across networks.

**What P4 validates.** P4 validates the *deployed rule base* itself. That base is evaluated
unchanged on the independent corpus (A.2). No selection is run on P4 data.

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

**Table A.1.** Test results at $\tau=65$: across-fold mean ± s.d. of per-fold seed medians.

| Protocol | Rules | CARS P / R / $F_1$ | CARS FPR | CARS NF$_1$ / NF$_0$ | $K_0$ $F_1$ / FPR | $K_0$ NF$_1$ / NF$_0$ |
|---|---|---|---|---|---|---|
| P1 | 15† | .975 / .863 / .915† | .0061† | 1.3% / 24.4%† | .850 / .0461† | 6.4% / 3.2%† |
| P2 | 15† | .977 / .724 / .832† | .0038† | 0.0% / 8.4%† | .783 / .0552† | 9.7% / 3.6%† |
| P3 (6 folds) | 12–19† | .965 / .760 / .836 ± .131† | .0064 ± .0015† | 7.7% / 30.9%† | .806 ± .151 / .0472 ± .0164† | 8.3% / 3.3%† |
| P4 (deployed base) | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] | [TBD] |

**Reading the preliminary coverage figures.** These † values come from the preliminary method.
They show that its bases left a large share of benign events with no firing rule (NF$_0$ up to
89.5% in fold S2†). That fraction of the low FPR arises by default, not by discrimination. The
revised procedure is judged on the same measure.

**Preliminary dominance.** Under one seed, the preliminary base dominated its seed base in
7 of 8 protocol/fold runs† (all except fold S5†).

**Precision.** Precision is measured at the tested attack prevalence of 15–28%. It does not
establish the false-alarm burden at deployment prevalence.

**Table A.2.** Deployed rule base (antecedent → $z$; features not listed are $\ast$).

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

**Interpretation of selection frequency.** Selection frequency measures how *stable* a rule is
under the specified procedure. It does not show that an individual rule is necessary or
independently correct. Seed rules are always available, whereas generated candidates may be
pruned or change consequent across folds, so the two kinds of rule are not directly
comparable.

**Table A.3.** Ablations under P2, P3 and P4 (seed medians).

| Variant | P2 $F_1$ / FPR | P3 $F_1$ / FPR | P4 $F_1$ / FPR | NF$_1$ / NF$_0$ |
|---|---|---|---|---|
| CARS (as specified) | .832 / .0038† | .836 / .0064† | [TBD] | [TBD] |
| Random initialization (same pool, $K_0$ not seeded) | [TBD] | [TBD] | [TBD] | [TBD] |
| Generated candidates only ($K_0$ and its privileges removed) | [TBD] | [TBD] | [TBD] | [TBD] |
| $K_0$ subject to pruning and data-assigned consequents | [TBD] | [TBD] | [TBD] | [TBD] |
| 0.5-centred confidence margin | [TBD] | [TBD] | [TBD] | [TBD] |
| Pre-activation events excluded | [TBD] | [TBD] | [TBD] | [TBD] |

Of these variants, only the generated-only one measures performance without the seed-rule prior.

## A.6 Limitations

- **Simulation scope.** Labels come from simulation ground truth, and the number of
  independent executions is small.
- **Dependence on $K_0$.** P1–P3 results for the seeded procedure are conditional on $K_0$,
  whose development may overlap their test data (A.3).
- **Design choices.** The membership functions, threshold, objective weights, bounds and seed
  base are choices made by the authors. CARS selects rules conditional on them; it does not
  optimise them.
- **Rule-level evidence.** Selection frequency shows stability, not necessity. The retention or
  absence of a seed rule does not show that it is correct or wrong.

## References

[1] L.-X. Wang and J. M. Mendel, "Generating fuzzy rules by learning from examples," *IEEE Trans. Syst., Man, Cybern.*, vol. 22, no. 6, pp. 1414–1427, 1992.
[2] H. Ishibuchi, T. Murata, and I. B. Türkşen, "Single-objective and two-objective genetic algorithms for selecting linguistic rules for pattern classification problems," *Fuzzy Sets Syst.*, vol. 89, no. 2, pp. 135–149, 1997.
[3] H. Ishibuchi and T. Yamamoto, "Fuzzy rule selection by multi-objective genetic local search algorithms and rule evaluation measures in data mining," *Fuzzy Sets Syst.*, vol. 141, no. 1, pp. 59–88, 2004.
[4] K. Deb, A. Pratap, S. Agarwal, and T. Meyarivan, "A fast and elitist multiobjective genetic algorithm: NSGA-II," *IEEE Trans. Evol. Comput.*, vol. 6, no. 2, pp. 182–197, 2002.
[5] S. Axelsson, "The base-rate fallacy and the difficulty of intrusion detection," *ACM Trans. Inf. Syst. Secur.*, vol. 3, no. 3, pp. 186–205, 2000.
