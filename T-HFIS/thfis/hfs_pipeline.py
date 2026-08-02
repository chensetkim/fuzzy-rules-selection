"""
hfs_pipeline.py -- Data-driven rule SELECTION for the T-HFIS hierarchy
=======================================================================
hierarchy.py ships one hand-designed 25-rule hierarchy (6 RA + 5 SI +
5 CX + 9 TOP), justified by tracing each sub-rule back to R1-R18. This
module runs the SAME candidate-generation + Ishibuchi-certainty-grade +
NSGA-II methodology used by the flat CARS/rs pipeline, but jointly over
the four T-HFIS sub-FIS units, so the hierarchy's rule content is chosen
by the same reproducible procedure as the flat base rather than only by
hand.

Per-unit candidate pools
-------------------------
  RA  inputs (v1,v3,v4)  -- full enumeration, <=3 terms (63 candidates)
  SI  inputs (v2,v5)     -- full enumeration, <=2 terms (15 candidates)
  CX  inputs (v6,v7)     -- full enumeration, <=2 terms (15 candidates)
  TOP inputs (RA,SI,CX)  -- full enumeration, <=3 terms (63 candidates),
                            built against a REFERENCE ra/si/cx signal
                            (the fixed hand-crafted RA_RULES/SI_RULES/
                            CX_RULES run with ALL rules on) so the TOP
                            pool's antecedent grid and Ishibuchi
                            consequents are stable and don't have to be
                            re-derived inside the optimisation loop.
Consequents assigned the same way as candidates.py: certainty grade
conf(r) = sum_{y=1} w_r / sum w_r, snapped to {0,25,50,75,100}, pruned by
min support and |conf-0.5| margin. The hand-crafted RA/SI/CX/TOP rules
from hierarchy.py are always merged in (flagged "expert"), exactly as
R1-R18 is merged into the flat pool.

Joint optimisation
-------------------
Chromosome = concatenation of 4 binary masks [RA|SI|CX|TOP]. Fitness
evaluation performs the REAL two-layer inference every time (ra, si, cx
are recomputed from whichever layer-1 rules are switched on in THAT
individual, then fed through the TOP rules switched on in that same
individual) -- only the pool's antecedent grid/consequents are fixed in
advance, never the selection. Objectives and constraints mirror
optimize.py: minimise (1-F1, FPR, total_rules/max_rules), with
total_rules in [min_rules, max_rules] (the Z1 RAM/flash budget).
"""
from __future__ import annotations
from itertools import combinations, product

import numpy as np
import pandas as pd

from fuzzy import (DONT_CARE, TERM_NAMES, Z_NAMES, MFConfig,
                   firing_matrix, sugeno_ac)
from candidates import assign_consequents
from optimize import f1_fpr
from hierarchy import THFIS, RA_RULES, SI_RULES, CX_RULES, TOP_RULES

from pymoo.core.problem import Problem
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.operators.sampling.rnd import BinaryRandomSampling
from pymoo.operators.crossover.ux import UniformCrossover
from pymoo.operators.mutation.bitflip import BitflipMutation
from pymoo.optimize import minimize
from pymoo.termination import get_termination

RA_IN = THFIS.RA_IN   # [0,2,3] -> v1,v3,v4
SI_IN = THFIS.SI_IN   # [1,4]   -> v2,v5
CX_IN = THFIS.CX_IN   # [5,6]   -> v6,v7

UNIT_INPUT_NAMES = {
    "RA": ["v1", "v3", "v4"],
    "SI": ["v2", "v5"],
    "CX": ["v6", "v7"],
    "TOP": ["RA", "SI", "CX"],
}

# ---------------------------------------------------------------------------
# Candidate pool construction (per unit)
# ---------------------------------------------------------------------------

def enumerate_local_antecedents(n_features: int, max_terms: int) -> np.ndarray:
    rows = []
    for k in range(1, max_terms + 1):
        for feats in combinations(range(n_features), k):
            for terms in product((1, 2, 3), repeat=k):
                ant = np.zeros(n_features, dtype=np.int8)
                ant[list(feats)] = terms
                rows.append(ant)
    return np.array(rows, dtype=np.int8)


def build_unit_pool(X_local: np.ndarray, y: np.ndarray, mf: MFConfig,
                    hand_rules: list, unit_tag: str,
                    max_terms: int | None = None,
                    min_support: float = 0.01, conf_margin: float = 0.15,
                    verbose: bool = True):
    """hand_rules: list of (name, antecedent_tuple, z, note) as in
    hierarchy.py's RA_RULES/SI_RULES/CX_RULES/TOP_RULES."""
    n_features = X_local.shape[1]
    if max_terms is None:
        max_terms = n_features
    M = mf.memberships(X_local)

    ants = enumerate_local_antecedents(n_features, max_terms)
    W = firing_matrix(M, ants)
    conf, support, z = assign_consequents(W, y)
    keep = (support >= min_support) & (np.abs(conf - 0.5) >= conf_margin)
    ants, z, conf, support = ants[keep], z[keep], conf[keep], support[keep]
    W = W[:, keep]
    names = [f"{unit_tag}G{i+1}" for i in range(len(ants))]
    expert_mask = np.zeros(len(ants), dtype=bool)

    e_ants = np.array([r[1] for r in hand_rules], dtype=np.int8)
    e_z = np.array([r[2] for r in hand_rules], dtype=np.float64)
    e_names = [r[0] for r in hand_rules]

    dup = (np.array([any((ea == a).all() for ea in e_ants) for a in ants])
          if len(ants) else np.zeros(0, dtype=bool))
    ants, z, conf, support = ants[~dup], z[~dup], conf[~dup], support[~dup]
    names = [n for n, d in zip(names, dup) if not d]
    W = W[:, ~dup]
    expert_mask = expert_mask[~dup]

    e_W = firing_matrix(M, e_ants)
    e_conf, e_support, _ = assign_consequents(e_W, y)
    ants = np.concatenate([ants, e_ants])
    z = np.concatenate([z, e_z])
    conf = np.concatenate([conf, e_conf])
    support = np.concatenate([support, e_support])
    W = np.concatenate([W, e_W], axis=1)
    names += e_names
    expert_mask = np.concatenate([expert_mask, np.ones(len(e_ants), dtype=bool)])

    if verbose:
        print(f"[pool:{unit_tag}] {len(ants)} candidates ({int(expert_mask.sum())} expert, "
              f"{len(hand_rules)} hand-crafted seeds)")
    return dict(antecedents=ants, z=z, conf=conf, support=support, names=names,
               expert_mask=expert_mask, W=W, n_features=n_features, tag=unit_tag)


def build_all_pools(X: np.ndarray, y: np.ndarray, mf: MFConfig,
                    min_support: float = 0.01, conf_margin: float = 0.15):
    """X: (n,7) raw v1..v7. Layer-1 pools built from raw features; the TOP
    pool is built from a REFERENCE ra/si/cx computed with the full
    hand-crafted hierarchy (all RA/SI/CX rules on)."""
    ra_pool = build_unit_pool(X[:, RA_IN], y, mf, RA_RULES, "A",
                              min_support=min_support, conf_margin=conf_margin)
    si_pool = build_unit_pool(X[:, SI_IN], y, mf, SI_RULES, "B",
                              min_support=min_support, conf_margin=conf_margin)
    cx_pool = build_unit_pool(X[:, CX_IN], y, mf, CX_RULES, "C",
                              min_support=min_support, conf_margin=conf_margin)

    ref = THFIS(mf)
    ra_ref, si_ref, cx_ref = ref.intermediates(X)
    Xtop_ref = np.stack([ra_ref, si_ref, cx_ref], axis=1)
    top_pool = build_unit_pool(Xtop_ref, y, mf, TOP_RULES, "T",
                               min_support=min_support, conf_margin=conf_margin)
    return ra_pool, si_pool, cx_pool, top_pool


def pool_dims(ra_pool, si_pool, cx_pool, top_pool):
    return [ra_pool["W"].shape[1], si_pool["W"].shape[1],
            cx_pool["W"].shape[1], top_pool["W"].shape[1]]


def split_mask(mask, dims):
    i = 0
    parts = []
    for d in dims:
        parts.append(mask[i:i + d])
        i += d
    return parts


def joint_expert_mask(ra_pool, si_pool, cx_pool, top_pool):
    return np.concatenate([ra_pool["expert_mask"], si_pool["expert_mask"],
                           cx_pool["expert_mask"], top_pool["expert_mask"]])


def hfs_infer(X: np.ndarray, ra_pool, si_pool, cx_pool, top_pool, mask, mf,
             dims=None):
    """Full two-layer inference on raw (n,7) features using whichever
    subset of each unit's pool `mask` selects. Returns (ac, (ra,si,cx))."""
    if dims is None:
        dims = pool_dims(ra_pool, si_pool, cx_pool, top_pool)
    ra_m, si_m, cx_m, top_m = split_mask(mask, dims)

    M_ra = mf.memberships(X[:, RA_IN])
    W_ra = firing_matrix(M_ra, ra_pool["antecedents"])
    ra = sugeno_ac(W_ra, ra_pool["z"], subset=ra_m)

    M_si = mf.memberships(X[:, SI_IN])
    W_si = firing_matrix(M_si, si_pool["antecedents"])
    si = sugeno_ac(W_si, si_pool["z"], subset=si_m)

    M_cx = mf.memberships(X[:, CX_IN])
    W_cx = firing_matrix(M_cx, cx_pool["antecedents"])
    cx = sugeno_ac(W_cx, cx_pool["z"], subset=cx_m)

    Xtop = np.stack([ra, si, cx], axis=1)
    M_top = mf.memberships(Xtop)
    W_top = firing_matrix(M_top, top_pool["antecedents"])
    ac = sugeno_ac(W_top, top_pool["z"], subset=top_m)
    return ac, (ra, si, cx)


# ---------------------------------------------------------------------------
# NSGA-II joint optimisation
# ---------------------------------------------------------------------------

class HFSSelectionProblem(Problem):
    def __init__(self, ra_pool, si_pool, cx_pool, top_pool, y, mf,
                ac_thr: float = 65.0, max_rules: int = 29, min_rules: int = 12):
        self.ra, self.si, self.cx, self.top = ra_pool, si_pool, cx_pool, top_pool
        self.y, self.mf, self.ac_thr = y, mf, ac_thr
        self.max_rules, self.min_rules = max_rules, min_rules
        self.dims = pool_dims(ra_pool, si_pool, cx_pool, top_pool)
        n_constr = 2 if min_rules > 0 else 1
        super().__init__(n_var=sum(self.dims), n_obj=3, n_constr=n_constr,
                         xl=0, xu=1, vtype=bool)

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
            ra_m, si_m, cx_m, top_m = split_mask(mask, self.dims)
            ra = sugeno_ac(self.ra["W"], self.ra["z"], subset=ra_m)
            si = sugeno_ac(self.si["W"], self.si["z"], subset=si_m)
            cx = sugeno_ac(self.cx["W"], self.cx["z"], subset=cx_m)
            Xtop = np.stack([ra, si, cx], axis=1)
            M_top = self.mf.memberships(Xtop)
            W_top = firing_matrix(M_top, self.top["antecedents"])
            ac = sugeno_ac(W_top, self.top["z"], subset=top_m)
            f1, fpr, _ = f1_fpr(ac, self.y, self.ac_thr)
            F[i] = [1.0 - f1, fpr, n / self.max_rules]
            G[i, 0] = n - self.max_rules
            if self.n_constr > 1:
                G[i, 1] = self.min_rules - n
        out["F"], out["G"] = F, G


def seeded_population_hfs(pool_size: int, pop_size: int, expert_mask: np.ndarray,
                          seed: int = 42, init_density: float = 0.05):
    rng = np.random.default_rng(seed)
    P = (rng.random((pop_size, pool_size)) < init_density)
    P[0] = expert_mask.copy()
    for i in range(1, min(10, pop_size)):
        v = expert_mask.copy()
        flips = rng.integers(0, pool_size, size=3)
        v[flips] = ~v[flips]
        P[i] = v
    return P


def run_nsga2_hfs(ra_pool, si_pool, cx_pool, top_pool, y, mf,
                  ac_thr: float = 65.0, max_rules: int = 29, min_rules: int = 12,
                  pop_size: int = 150, n_gen: int = 250, seed: int = 42):
    problem = HFSSelectionProblem(ra_pool, si_pool, cx_pool, top_pool, y, mf,
                                  ac_thr=ac_thr, max_rules=max_rules,
                                  min_rules=min_rules)
    expert_mask = joint_expert_mask(ra_pool, si_pool, cx_pool, top_pool)
    init = seeded_population_hfs(problem.n_var, pop_size, expert_mask, seed=seed)
    algo = NSGA2(pop_size=pop_size, sampling=init.astype(bool),
                crossover=UniformCrossover(prob=0.9),
                mutation=BitflipMutation(prob=1.0, prob_var=1.0 / problem.n_var),
                eliminate_duplicates=True)
    res = minimize(problem, algo, get_termination("n_gen", n_gen), seed=seed,
                   verbose=True)
    masks = res.X.astype(bool)
    if masks.ndim == 1:
        masks = masks[None, :]
    return masks, res.F, problem.dims


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def overlap_stats(mask, expert_mask):
    sel = set(np.nonzero(mask)[0])
    exp = set(np.nonzero(expert_mask)[0])
    inter = len(sel & exp)
    union = len(sel | exp)
    n_expert = len(exp)
    return dict(n_selected=len(sel), n_expert_in_base=inter,
               jaccard=inter / union if union else 0.0,
               expert_coverage=inter / n_expert if n_expert else 0.0)


def _mask_names(pool, unit_mask):
    return [pool["names"][j] for j in np.nonzero(unit_mask)[0]]


def hfs_pareto_table(masks, F, dims, ra_pool, si_pool, cx_pool, top_pool, mf,
                     X_te, y_te, ac_thr):
    expert_mask = joint_expert_mask(ra_pool, si_pool, cx_pool, top_pool)
    rows = []
    for i, mask in enumerate(masks):
        ra_m, si_m, cx_m, top_m = split_mask(mask, dims)
        ac_te, _ = hfs_infer(X_te, ra_pool, si_pool, cx_pool, top_pool, mask, mf, dims)
        f1_te, fpr_te, cm_te = f1_fpr(ac_te, y_te, ac_thr)
        ov = overlap_stats(mask, expert_mask)
        rule_names = ("RA:" + ",".join(_mask_names(ra_pool, ra_m)) +
                     "|SI:" + ",".join(_mask_names(si_pool, si_m)) +
                     "|CX:" + ",".join(_mask_names(cx_pool, cx_m)) +
                     "|TOP:" + ",".join(_mask_names(top_pool, top_m)))
        rows.append(dict(base_id=i, n_rules=int(mask.sum()),
                         n_ra=int(ra_m.sum()), n_si=int(si_m.sum()),
                         n_cx=int(cx_m.sum()), n_top=int(top_m.sum()),
                         f1_train=round(1.0 - F[i, 0], 4),
                         fpr_train=round(F[i, 1], 4),
                         f1_test=round(f1_te, 4), fpr_test=round(fpr_te, 4),
                         recall_test=round(cm_te["recall"], 4),
                         precision_test=round(cm_te["precision"], 4),
                         expert_rules_included=ov["n_expert_in_base"],
                         jaccard_vs_expert=round(ov["jaccard"], 3),
                         rules=rule_names))
    return pd.DataFrame(rows).sort_values(["f1_test", "n_rules"], ascending=[False, True])


def rule_str_named(ant, z, feat_names) -> str:
    terms = [f"{feat_names[i]} is {TERM_NAMES[t]}" for i, t in enumerate(ant) if t != DONT_CARE]
    return "IF " + " AND ".join(terms) + f" THEN out = {Z_NAMES[int(z)]} ({int(z)})"


def _unit_listing(pool, mask, unit_key):
    names = UNIT_INPUT_NAMES[unit_key]
    lines = []
    for j in np.nonzero(mask)[0]:
        tag = "[expert]" if pool["expert_mask"][j] else "[generated]"
        lines.append(f"  {pool['names'][j]:>8} {tag:11} "
                     f"{rule_str_named(pool['antecedents'][j], pool['z'][j], names)}  "
                     f"(support={pool['support'][j]:.3f}, conf={pool['conf'][j]:.2f})")
    return "\n".join(lines)


def rules_listing_hfs(mask, dims, ra_pool, si_pool, cx_pool, top_pool):
    ra_m, si_m, cx_m, top_m = split_mask(mask, dims)
    out = []
    out.append(f"== RA: Rank-trajectory Anomaly  (inputs v1,v3,v4)  {int(ra_m.sum())} rules ==")
    out.append(_unit_listing(ra_pool, ra_m, "RA"))
    out.append(f"\n== SI: Signal Instability  (inputs v2,v5)  {int(si_m.sum())} rules ==")
    out.append(_unit_listing(si_pool, si_m, "SI"))
    out.append(f"\n== CX: Corroboration/Context  (inputs v6,v7)  {int(cx_m.sum())} rules ==")
    out.append(_unit_listing(cx_pool, cx_m, "CX"))
    out.append(f"\n== TOP: Decision  (inputs RA,SI,CX)  {int(top_m.sum())} rules ==")
    out.append(_unit_listing(top_pool, top_m, "TOP"))
    return "\n".join(out)


MU_FN = {1: "mu_L", 2: "mu_M", 3: "mu_H"}


def _export_unit_c(pool, mask, out_name, feat_names, lines):
    idx = np.nonzero(mask)[0]
    n = len(idx)
    lines.append(f"/* {out_name}: {n} rules */")
    lines.append(f"uint16_t w_{out_name.lower()}[{n + 1}]; uint8_t zc_{out_name.lower()}[{n + 1}];")
    for r, j in enumerate(idx, start=1):
        ant, z = pool["antecedents"][j], int(pool["z"][j])
        terms = [(feat_names[i], t) for i, t in enumerate(ant) if t != DONT_CARE]
        expr = f"{MU_FN[terms[0][1]]}({terms[0][0]})"
        for feat, t in terms[1:]:
            expr = f"min2({expr}, {MU_FN[t]}({feat}))"
        cond = " AND ".join(f"{f} is {TERM_NAMES[t]}" for f, t in terms)
        lines.append(f"/* {pool['names'][j]}: {cond} -> {z} */")
        lines.append(f"w_{out_name.lower()}[{r}] = {expr};  zc_{out_name.lower()}[{r}] = {z};")
    lines.append(f"uint32_t num_{out_name.lower()} = 0, den_{out_name.lower()} = 1;")
    lines.append(f"for(r = 1; r <= {n}; r++) {{ num_{out_name.lower()} += "
                f"(uint32_t)w_{out_name.lower()}[r] * zc_{out_name.lower()}[r]; "
                f"den_{out_name.lower()} += w_{out_name.lower()}[r]; }}")
    lines.append(f"uint8_t {out_name.lower()} = (uint8_t)(num_{out_name.lower()} / den_{out_name.lower()});")
    lines.append("")


def export_c_hfs(mask, dims, ra_pool, si_pool, cx_pool, top_pool, fname):
    ra_m, si_m, cx_m, top_m = split_mask(mask, dims)
    lines = [f"/* Auto-generated by hfs_pipeline rule selection: "
            f"{int(mask.sum())} rules total "
            f"({int(ra_m.sum())}+{int(si_m.sum())}+{int(cx_m.sum())}+{int(top_m.sum())}) */", ""]
    _export_unit_c(ra_pool, ra_m, "ra", ["v1", "v3", "v4"], lines)
    _export_unit_c(si_pool, si_m, "si", ["v2", "v5"], lines)
    _export_unit_c(cx_pool, cx_m, "cx", ["v6", "v7"], lines)
    _export_unit_c(top_pool, top_m, "ac", ["ra", "si", "cx"], lines)
    lines.append("return ac;  /* AC in 0..100 */")
    with open(fname, "w") as f:
        f.write("\n".join(lines) + "\n")
