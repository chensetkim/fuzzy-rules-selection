"""
optimize.py -- Multi-objective rule-subset selection (NSGA-II)
==============================================================
Chromosome: binary vector over the candidate pool (1 = rule included).
Objectives (all minimised), following Ishibuchi & Yamamoto's
accuracy/complexity trade-off formulation for fuzzy rule selection:

    f1 = 1 - F1(train)          detection quality
    f2 = FPR(train)             false-positive burden (the deployment cost
                                the paper's High-set design targets)
    f3 = |S| / max_rules        rule-base size (RAM/flash on Z1, and
                                interpretability)

Classification: a sample is flagged when Sugeno AC >= ac_thr (default 65,
matching FUZZRID_TAU_Q_PCT / compute_metrics.py AC_THR).

The expert 18-rule base is injected into the initial population, plus
mutated neighbours of it, so the optimizer starts from (and must beat or
join) the taxonomy-derived solution rather than ignore it.
"""

from __future__ import annotations
import numpy as np

from pymoo.core.problem import Problem
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.operators.sampling.rnd import BinaryRandomSampling
from pymoo.operators.crossover.ux import UniformCrossover
from pymoo.operators.mutation.bitflip import BitflipMutation
from pymoo.optimize import minimize
from pymoo.termination import get_termination

from fuzzy import sugeno_ac


def f1_fpr(ac: np.ndarray, y: np.ndarray, ac_thr: float = 65.0):
    pred = ac >= ac_thr
    tp = int(np.sum(pred & (y == 1)))
    fp = int(np.sum(pred & (y == 0)))
    fn = int(np.sum(~pred & (y == 1)))
    tn = int(np.sum(~pred & (y == 0)))
    prec = tp / (tp + fp) if tp + fp else 0.0
    rec = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
    fpr = fp / (fp + tn) if fp + tn else 0.0
    return f1, fpr, dict(tp=tp, fp=fp, fn=fn, tn=tn, precision=prec, recall=rec)


class RuleSelectionProblem(Problem):
    def __init__(self, W: np.ndarray, z: np.ndarray, y: np.ndarray,
                 ac_thr: float = 65.0, max_rules: int = 30, min_rules: int = 0):
        self.W, self.z, self.y = W, z, y
        self.ac_thr, self.max_rules, self.min_rules = ac_thr, max_rules, min_rules
        n_constr = 2 if min_rules > 0 else 1
        super().__init__(n_var=W.shape[1], n_obj=3, n_constr=n_constr, xl=0, xu=1,
                         vtype=bool)

    def _evaluate(self, Xpop, out, *args, **kwargs):
        F = np.empty((len(Xpop), 3))
        G = np.empty((len(Xpop), self.n_constr))
        for i, mask in enumerate(Xpop.astype(bool)):
            n = int(mask.sum())
            if n == 0:
                F[i] = [1.0, 1.0, 0.0]
                G[i, 0] = 1.0
                if self.n_constr > 1:
                    G[i, 1] = self.min_rules
                continue
            ac = sugeno_ac(self.W, self.z, subset=mask)
            f1, fpr, _ = f1_fpr(ac, self.y, self.ac_thr)
            F[i] = [1.0 - f1, fpr, n / self.max_rules]
            G[i, 0] = n - self.max_rules       # constraint: |S| <= max_rules
            if self.n_constr > 1:
                G[i, 1] = self.min_rules - n   # constraint: |S| >= min_rules
        out["F"], out["G"] = F, G


def seeded_population(pool_size: int, pop_size: int, expert_mask: np.ndarray,
                      seed: int = 42, init_density: float = 0.02):
    """Random sparse individuals + the expert base + mutated expert variants."""
    rng = np.random.default_rng(seed)
    P = (rng.random((pop_size, pool_size)) < init_density)
    P[0] = expert_mask.copy()                        # the taxonomy-derived base
    for i in range(1, min(10, pop_size)):            # neighbourhood of it
        v = expert_mask.copy()
        flips = rng.integers(0, pool_size, size=3)
        v[flips] = ~v[flips]
        P[i] = v
    return P


def run_nsga2(pool: dict, y: np.ndarray, ac_thr: float = 65.0,
              max_rules: int = 30, min_rules: int = 0, pop_size: int = 120,
              n_gen: int = 200, seed: int = 42, verbose: bool = True):
    W, z, expert_mask = pool["W"], pool["z"], pool["expert_mask"]
    problem = RuleSelectionProblem(W, z, y, ac_thr=ac_thr, max_rules=max_rules,
                                   min_rules=min_rules)

    init = seeded_population(W.shape[1], pop_size, expert_mask, seed=seed)
    algo = NSGA2(pop_size=pop_size,
                 sampling=init.astype(bool),
                 crossover=UniformCrossover(prob=0.9),
                 mutation=BitflipMutation(prob=1.0, prob_var=1.0 / W.shape[1]),
                 eliminate_duplicates=True)
    res = minimize(problem, algo, get_termination("n_gen", n_gen),
                   seed=seed, verbose=verbose)
    masks = res.X.astype(bool)
    if masks.ndim == 1:
        masks = masks[None, :]
    return masks, res.F


def knee_solution(F: np.ndarray, w=(0.6, 0.3, 0.1)) -> int:
    """Pick one Pareto solution by weighted normalised distance to the ideal
    point -- weights favour detection quality, then FPR, then compactness."""
    Fn = (F - F.min(axis=0)) / (np.ptp(F, axis=0) + 1e-12)
    score = (np.array(w) * Fn).sum(axis=1)
    return int(np.argmin(score))
