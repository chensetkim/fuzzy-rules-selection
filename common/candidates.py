"""
candidates.py -- Candidate rule pool generation
================================================
Two complementary generators feed one pruned candidate pool:

1. Wang-Mendel (WM) generation [Wang & Mendel, IEEE TSMC 1992]:
   each training sample produces the full-antecedent rule of the fuzzy
   cell it belongs to (argmax membership per feature). This anchors the
   pool in regions of the 3^7 grid that the data actually occupies.

2. Bounded exhaustive enumeration: all partial antecedents using at most
   `max_terms` features (sum_k C(7,k) * 3^k; for max_terms=4 this is 3,990
   candidates). This covers the compact, interpretable rules the deployed
   18-rule base is made of, which WM's full-length rules cannot express.

Consequent assignment (Ishibuchi-style certainty grade): for candidate
rule r with firing strengths w_r(x) over the training set,

    conf(r) = sum_{y=1} w_r(x) / sum_all w_r(x)

and z_r = the singleton in {0,25,50,75,100} nearest to 100*conf(r).
Pruning keeps rules with support >= min_support and |conf-0.5| >= margin
(rules that cannot discriminate carry no selective value).

The expert base R1-R18 is always merged into the pool (flagged), so
NSGA-II selects over expert and generated rules on equal footing.
"""

from __future__ import annotations
from itertools import combinations, product
import numpy as np

from fuzzy import (N_FEATURES, DONT_CARE, Z_LEVELS, MFConfig,
                   firing_matrix, expert_arrays)


def wang_mendel_antecedents(M: np.ndarray, max_rules: int | None = None) -> np.ndarray:
    """Full-antecedent WM rules: per sample, term = argmax membership per
    feature. Returns unique (n,7) int8 antecedents (terms 1..3, no
    don't-cares)."""
    terms = M.argmax(axis=2) + 1                     # (n_samples, 7) in 1..3
    uniq, counts = np.unique(terms, axis=0, return_counts=True)
    order = np.argsort(-counts)
    uniq = uniq[order]
    if max_rules is not None:
        uniq = uniq[:max_rules]
    return uniq.astype(np.int8)


def enumerate_antecedents(max_terms: int = 4) -> np.ndarray:
    """All partial antecedents with 1..max_terms specified features."""
    rows = []
    for k in range(1, max_terms + 1):
        for feats in combinations(range(N_FEATURES), k):
            for terms in product((1, 2, 3), repeat=k):
                ant = np.zeros(N_FEATURES, dtype=np.int8)
                ant[list(feats)] = terms
                rows.append(ant)
    return np.array(rows, dtype=np.int8)


def assign_consequents(W: np.ndarray, y: np.ndarray):
    """conf, support, z for each candidate given firing matrix W and labels y."""
    w_pos = W[y == 1].sum(axis=0)
    w_all = W.sum(axis=0)
    with np.errstate(divide="ignore", invalid="ignore"):
        conf = np.where(w_all > 0, w_pos / w_all, 0.0)
    support = w_all / max(len(y), 1)
    z = Z_LEVELS[np.abs(conf[:, None] * 100 - Z_LEVELS[None, :]).argmin(axis=1)]
    return conf, support, z.astype(np.float64)


def build_pool(X: np.ndarray, y: np.ndarray, mf: MFConfig,
               max_terms: int = 4,
               min_support: float = 0.005,
               conf_margin: float = 0.15,
               wm_max_rules: int = 200,
               include_expert: bool = True,
               verbose: bool = True):
    """Returns dict with antecedents (P,7), z (P,), conf, support, names,
    expert_mask (bool P,), and the precomputed firing matrix W (n,P)."""
    M = mf.memberships(X)

    ants_enum = enumerate_antecedents(max_terms)
    ants_wm = wang_mendel_antecedents(M, max_rules=wm_max_rules)
    ants = np.concatenate([ants_enum, ants_wm], axis=0)
    src = (["enum"] * len(ants_enum)) + (["wm"] * len(ants_wm))

    # Deduplicate (WM rules may duplicate nothing here since enum is <=4 terms
    # and WM is 7 terms, but keep it robust).
    ants, uniq_idx = np.unique(ants, axis=0, return_index=True)
    src = [src[i] for i in uniq_idx]

    W = firing_matrix(M, ants)
    conf, support, z = assign_consequents(W, y)

    keep = (support >= min_support) & (np.abs(conf - 0.5) >= conf_margin)
    ants, z, conf, support = ants[keep], z[keep], conf[keep], support[keep]
    src = [s for s, k in zip(src, keep) if k]
    W = W[:, keep]
    names = [f"G{i+1}({s})" for i, s in enumerate(src)]
    expert_mask = np.zeros(len(ants), dtype=bool)

    if include_expert:
        e_ants, e_z, e_names = expert_arrays()
        # Drop generated duplicates of expert rules (same antecedent);
        # expert copy wins so consequents stay firmware-faithful.
        dup = np.array([any((ea == a).all() for ea in e_ants) for a in ants])
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
        print(f"[pool] enumerated={len(ants_enum)}  wang-mendel={len(ants_wm)}  "
              f"after pruning+expert merge={len(ants)} candidates "
              f"({int(expert_mask.sum())} expert)")
    return dict(antecedents=ants, z=z, conf=conf, support=support,
                names=names, expert_mask=expert_mask, W=W)
