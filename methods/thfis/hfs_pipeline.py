"""
hfs_pipeline.py -- Data-driven rule SELECTION for the T-HFIS hierarchy
=======================================================================
hierarchy.py defines only the layout (which inputs feed RA/SI/CX/TOP).
This module chooses every rule from data, with the SAME candidate-generation
+ Ishibuchi-certainty-grade + NSGA-II methodology as the flat methods/cars
pipeline, run jointly over the four T-HFIS sub-FIS units.

Per-unit candidate pools
-------------------------
  RA  inputs (v1,v3,v4)  -- full enumeration, <=3 terms (63 candidates)
  SI  inputs (v2,v5)     -- full enumeration, <=2 terms (15 candidates)
  CX  inputs (v6,v7)     -- full enumeration, <=2 terms (15 candidates)
  TOP inputs (RA,SI,CX)  -- full enumeration, <=3 terms (63 candidates),
                            built against a REFERENCE ra/si/cx signal
                            (the data-driven RA/SI/CX pools above run
                            with ALL their rules on) so the TOP
                            pool's antecedent grid and Ishibuchi
                            consequents are stable and don't have to be
                            re-derived inside the optimisation loop.
Consequents assigned the same way as candidates.py: certainty grade
conf(r) = sum_{y=1} w_r / sum w_r, snapped to {0,25,50,75,100}, pruned by
min support and |conf-0.5| margin. No hand-crafted rules are used.

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
from hierarchy import RA_IN, SI_IN, CX_IN, UNIT_INPUT_NAMES

from pymoo.core.problem import Problem
from pymoo.algorithms.moo.nsga2 import NSGA2
from pymoo.operators.sampling.rnd import BinaryRandomSampling
from pymoo.operators.crossover.ux import UniformCrossover
from pymoo.operators.mutation.bitflip import BitflipMutation
from pymoo.optimize import minimize
from pymoo.termination import get_termination


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
                    unit_tag: str,
                    max_terms: int | None = None,
                    min_support: float = 0.01, conf_margin: float = 0.15,
                    verbose: bool = True):
    """Fully enumerated, pruned candidate pool for one unit."""
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

    if verbose:
        print(f"[pool:{unit_tag}] {len(ants)} candidates")
    return dict(antecedents=ants, z=z, conf=conf, support=support, names=names,
               W=W, n_features=n_features, tag=unit_tag)


def build_all_pools(X: np.ndarray, y: np.ndarray, mf: MFConfig,
                    min_support: float = 0.01, conf_margin: float = 0.15):
    """X: (n,7) raw v1..v7. Layer-1 pools built from raw features; the TOP
    pool is built from a REFERENCE ra/si/cx computed with every rule of
    the data-driven layer-1 pools on."""
    ra_pool = build_unit_pool(X[:, RA_IN], y, mf, "A",
                              min_support=min_support, conf_margin=conf_margin)
    si_pool = build_unit_pool(X[:, SI_IN], y, mf, "B",
                              min_support=min_support, conf_margin=conf_margin)
    cx_pool = build_unit_pool(X[:, CX_IN], y, mf, "C",
                              min_support=min_support, conf_margin=conf_margin)

    ra_ref = sugeno_ac(ra_pool["W"], ra_pool["z"])
    si_ref = sugeno_ac(si_pool["W"], si_pool["z"])
    cx_ref = sugeno_ac(cx_pool["W"], cx_pool["z"])
    Xtop_ref = np.stack([ra_ref, si_ref, cx_ref], axis=1)
    top_pool = build_unit_pool(Xtop_ref, y, mf, "T",
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
                ac_thr: float = 65.0, max_rules: int = 35, min_rules: int = 12):
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


def random_population_hfs(pool_size: int, pop_size: int, seed: int = 42,
                          init_density: float = 0.05):
    rng = np.random.default_rng(seed)
    return rng.random((pop_size, pool_size)) < init_density


def run_nsga2_hfs(ra_pool, si_pool, cx_pool, top_pool, y, mf,
                  ac_thr: float = 65.0, max_rules: int = 35, min_rules: int = 12,
                  pop_size: int = 150, n_gen: int = 250, seed: int = 42):
    problem = HFSSelectionProblem(ra_pool, si_pool, cx_pool, top_pool, y, mf,
                                  ac_thr=ac_thr, max_rules=max_rules,
                                  min_rules=min_rules)
    init = random_population_hfs(problem.n_var, pop_size, seed=seed)
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

def _mask_names(pool, unit_mask):
    return [pool["names"][j] for j in np.nonzero(unit_mask)[0]]


def hfs_pareto_table(masks, F, dims, ra_pool, si_pool, cx_pool, top_pool, mf,
                     X_te, y_te, ac_thr):
    rows = []
    for i, mask in enumerate(masks):
        ra_m, si_m, cx_m, top_m = split_mask(mask, dims)
        ac_te, _ = hfs_infer(X_te, ra_pool, si_pool, cx_pool, top_pool, mask, mf, dims)
        f1_te, fpr_te, cm_te = f1_fpr(ac_te, y_te, ac_thr)
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
                         rules=rule_names))
    return pd.DataFrame(rows).sort_values(["f1_test", "n_rules"], ascending=[False, True])


def rule_str_named(ant, z, feat_names) -> str:
    terms = [f"{feat_names[i]} is {TERM_NAMES[t]}" for i, t in enumerate(ant) if t != DONT_CARE]
    return "IF " + " AND ".join(terms) + f" THEN out = {Z_NAMES[int(z)]} ({int(z)})"


def _unit_listing(pool, mask, unit_key):
    names = UNIT_INPUT_NAMES[unit_key]
    lines = []
    for j in np.nonzero(mask)[0]:
        lines.append(f"  {pool['names'][j]:>8} "
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


def _export_unit_fn(pool, mask, fn, params, lines):
    """One static C function computing a unit's Sugeno output from its inputs."""
    idx = np.nonzero(mask)[0]
    n = len(idx)
    lines.append(f"static uint8_t {fn}({', '.join('uint8_t ' + p for p in params)})")
    lines.append("{")
    if n == 0:
        lines.append("  " + " ".join(f"(void){p};" for p in params) + "  /* no rules selected */")
        lines.append("  return 0;")
        lines.append("}")
        lines.append("")
        return
    used = set()
    lines.append(f"  uint8_t w[{n}], z[{n}];")
    for r, j in enumerate(idx):
        ant, zz = pool["antecedents"][j], int(pool["z"][j])
        terms = [(params[i], t) for i, t in enumerate(ant) if t != DONT_CARE]
        used.update(f for f, _ in terms)
        expr = f"{MU_FN[terms[0][1]]}({terms[0][0]})"
        for feat, t in terms[1:]:
            expr = f"min2({expr}, {MU_FN[t]}({feat}))"
        cond = " AND ".join(f"{f} is {TERM_NAMES[t]}" for f, t in terms)
        lines.append(f"  /* {pool['names'][j]}: {cond} -> {zz} */")
        lines.append(f"  w[{r}] = {expr};  z[{r}] = {zz};")
    for p in params:
        if p not in used:
            lines.append(f"  (void){p};  /* input not used by the selected rules */")
    lines.append(f"  return sugeno(w, z, {n});")
    lines.append("}")
    lines.append("")


def export_c_hfs(mask, dims, ra_pool, si_pool, cx_pool, top_pool, fname, mf: MFConfig):
    """Write a complete, compilable fuzzrid-fuzzy-hfs.c for the selected hierarchy:
    integer MFs with this run's breakpoints, the eps=1 Sugeno average, the four
    unit functions, and the two entry points declared in fuzzrid-fuzzy-hfs.h.
    Bit-exact with hfs_infer() under integer arithmetic (fuzzy.set_arithmetic("int"))."""
    ra_m, si_m, cx_m, top_m = split_mask(mask, dims)
    (la, lb), (mp, mq, mr), (hc, hd) = mf.low, mf.med, mf.high
    L = [
        "/*",
        " * fuzzrid-fuzzy-hfs.c -- T-HFIS hierarchical fuzzy engine.",
        " * AUTO-GENERATED by methods/thfis/hfs_pipeline.py (export_c_hfs); do not edit by hand.",
        f" * Selected hierarchy: {int(mask.sum())} rules "
        f"(RA {int(ra_m.sum())} + SI {int(si_m.sum())} + CX {int(cx_m.sum())} + TOP {int(top_m.sum())}).",
        " * Integer-only, same MF family and arithmetic as fuzzrid-fuzzy.c:",
        " * uint8 memberships 0..100 (truncating division), min t-norm,",
        " * AC = sum(w*z) / (1 + sum(w)). Copy over apps/2h-fuzzrid/fuzzrid-fuzzy-hfs.c.",
        " */",
        "",
        "#include <stdint.h>",
        '#include "fuzzrid-fuzzy-hfs.h"',
        "",
        f"/* Low: 100 on [0,{la}], linear to 0 at {lb}.  Medium: 0 at {mp}, 100 at {mq}, 0 at {mr}.",
        f" * High: 0 at {hc}, linear to 100 at {hd}, 100 on [{hd},100]. */",
        "static uint8_t mu_L(uint8_t v)",
        "{",
        f"  if(v <= {la}) return 100;",
        f"  if(v >= {lb}) return 0;",
        f"  return (uint8_t)((({lb} - v) * 100u) / {lb - la}u);",
        "}",
        "",
        "static uint8_t mu_M(uint8_t v)",
        "{",
        f"  if(v <= {mp} || v >= {mr}) return 0;",
        f"  if(v <= {mq}) return (uint8_t)(((v - {mp}) * 100u) / {mq - mp}u);",
        f"  return (uint8_t)((({mr} - v) * 100u) / {mr - mq}u);",
        "}",
        "",
        "static uint8_t mu_H(uint8_t v)",
        "{",
        f"  if(v <= {hc}) return 0;",
        f"  if(v >= {hd}) return 100;",
        f"  return (uint8_t)(((v - {hc}) * 100u) / {hd - hc}u);",
        "}",
        "",
        "static uint8_t min2(uint8_t a, uint8_t b) { return a < b ? a : b; }",
        "",
        "/* Sugeno weighted average, epsilon = 1, weights on the 0..100 scale */",
        "static uint8_t sugeno(const uint8_t *w, const uint8_t *z, uint8_t n)",
        "{",
        "  uint32_t num = 0, den = 1;",
        "  uint8_t r;",
        "  for(r = 0; r < n; r++) {",
        "    num += (uint32_t)w[r] * z[r];",
        "    den += w[r];",
        "  }",
        "  return (uint8_t)(num / den);",
        "}",
        "",
    ]
    _export_unit_fn(ra_pool, ra_m, "infer_ra", ["v1", "v3", "v4"], L)
    _export_unit_fn(si_pool, si_m, "infer_si", ["v2", "v5"], L)
    _export_unit_fn(cx_pool, cx_m, "infer_cx", ["v6", "v7"], L)
    _export_unit_fn(top_pool, top_m, "infer_top", ["ra", "si", "cx"], L)
    L += [
        "uint8_t",
        "fuzzrid_fuzzy_infer_ac_hfs(uint8_t v1, uint8_t v2, uint8_t v3, uint8_t v4,",
        "                           uint8_t v5, uint8_t v6, uint8_t v7)",
        "{",
        "  return infer_top(infer_ra(v1, v3, v4), infer_si(v2, v5), infer_cx(v6, v7));",
        "}",
        "",
        "/* Same, exposing the layer-1 intermediates for logging. Any out-pointer may be NULL. */",
        "uint8_t",
        "fuzzrid_fuzzy_infer_ac_hfs_x(uint8_t v1, uint8_t v2, uint8_t v3, uint8_t v4,",
        "                             uint8_t v5, uint8_t v6, uint8_t v7,",
        "                             uint8_t *ra_out, uint8_t *si_out, uint8_t *cx_out)",
        "{",
        "  uint8_t ra = infer_ra(v1, v3, v4);",
        "  uint8_t si = infer_si(v2, v5);",
        "  uint8_t cx = infer_cx(v6, v7);",
        "  if(ra_out) *ra_out = ra;",
        "  if(si_out) *si_out = si;",
        "  if(cx_out) *cx_out = cx;",
        "  return infer_top(ra, si, cx);",
        "}",
    ]
    with open(fname, "w") as f:
        f.write("\n".join(L) + "\n")
