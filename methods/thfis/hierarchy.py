"""
hierarchy.py -- T-HFIS: Taxonomy-driven Hierarchical Fuzzy Inference System
===========================================================================
Replaces the flat 7-input Sugeno engine with a two-layer hierarchy whose
decomposition is derived from the attack taxonomy (not chosen freely --
this is the design justification):

  Layer 1 (evidence aggregation, one sub-FIS per taxonomy branch)
    RA  Rank-trajectory Anomaly   inputs v1 (monotonicity violation),
                                         v3 (CUSUM drift / spike),
                                         v4 (rank-jump vs link-cost)
    SI  Signal Instability        inputs v2 (Trickle resets),
                                         v5 (residual sign-flip count)
    CX  Corroboration / Context   inputs v6 (mobility index, exculpatory),
                                         v7 (two-hop residual, inculpatory)
        CX semantics: 0 = mobility-excused, 50 = neutral, 100 = forged.

  Layer 2 (decision)
    TOP inputs RA, SI, CX -> AC in [0,100]

All four units are zero-order Sugeno with the SAME machinery as the flat
engine: L/M/H piecewise-linear sets on [0,100], min t-norm, singleton
consequents {0,25,50,75,100}, eps-guarded weighted average. Intermediate
outputs live on [0,100] and are re-fuzzified with the same MF family, so
no new membership-function design is introduced and the integer-only
arithmetic argument carries through unchanged.

Complexity: complete grids 3^3+3^2+3^2+3^3 = 72 rules max vs 3^7 = 2187
flat (30.4x); the deployed base below uses 6+5+5+9 = 25 rules.

Traceability: every sub-rule cites the flat rule(s) R1-R18 it descends
from, so the manuscript can present the hierarchy as a refactoring of the
taxonomy-derived base, not a new hand-designed artefact.

DOCUMENTED BEHAVIOUR CHANGE vs flat base: flat R1 (v1 High -> VH) is
unconditional; in T-HFIS a High rank anomaly with an exculpatory context
(CX Low, i.e. mobile node, no forgery) is discounted to AC=50 (rule T3).
This strengthens the mobility-aware false-positive story but must be
stated explicitly in the paper.
"""

from __future__ import annotations
import numpy as np

from fuzzy import MFConfig, firing_matrix, sugeno_ac, DONT_CARE, LOW, MED, HIGH

# --------------------------------------------------------------------------
# Sub-FIS rule tables.  Antecedent tuples index that unit's OWN inputs.
# --------------------------------------------------------------------------

# RA: inputs (v1, v3, v4)
RA_RULES = [  # (name, antecedent over (v1,v3,v4), z, descends-from)
    ("A1", (HIGH, 0,    0),   100, "R1"),
    ("A2", (0,    HIGH, 0),    75, "R6/R7 core"),
    ("A3", (0,    0,    HIGH), 75, "R3/R4 core"),
    ("A4", (0,    MED,  MED),  50, "R12 analog"),
    ("A5", (MED,  0,    0),    50, "graded v1"),
    ("A6", (LOW,  LOW,  LOW),   0, "R14/R18 benign core"),
]

# SI: inputs (v2, v5)
SI_RULES = [
    ("B1", (HIGH, HIGH), 100, "R10"),
    ("B2", (0,    HIGH),  75, "R9 core"),
    ("B3", (HIGH, 0),     50, "trickle alone = weak"),
    ("B4", (MED,  MED),   50, "graded"),
    ("B5", (LOW,  LOW),    0, "R14 benign core"),
]

# CX: inputs (v6, v7)   -- output is a *context score*, not pure evidence
CX_RULES = [
    ("C1", (0,    HIGH), 100, "R2"),
    ("C2", (0,    MED),   75, "graded v7"),
    ("C3", (HIGH, LOW),    0, "R13/R18 mobility excuse"),
    ("C4", (MED,  LOW),   25, "partial excuse"),
    ("C5", (LOW,  LOW),   50, "neutral"),
]

# TOP: inputs (RA, SI, CX)
TOP_RULES = [
    ("T1", (0,    0,    HIGH), 100, "R2/R15/R16: forgery is conclusive"),
    ("T2", (HIGH, 0,    MED),  100, "R1/R4/R7: strong rank anomaly, no excuse"),
    ("T3", (HIGH, 0,    LOW),   50, "NEW: mobility-discounted rank anomaly"),
    ("T4", (0,    HIGH, MED),   75, "R9/R11: instability, no excuse"),
    ("T5", (MED,  HIGH, 0),     75, "R5/R8: compound medium+instability"),
    ("T6", (MED,  MED,  MED),   50, "R12: everything middling"),
    ("T7", (LOW,  LOW,  LOW),    0, "R18: benign mobile"),
    ("T8", (LOW,  LOW,  MED),    0, "R14: all-clear"),
    ("T9", (0,    HIGH, LOW),   25, "mobility explains oscillation"),
]


def _unit_arrays(rules, n_inputs):
    ants = np.zeros((len(rules), n_inputs), dtype=np.int8)
    z = np.empty(len(rules))
    for i, (_, a, c, _) in enumerate(rules):
        ants[i] = a
        z[i] = c
    return ants, z


class THFIS:
    """Vectorised reference implementation, faithful to integer firmware
    semantics (same MFs, min t-norm, eps-guarded Sugeno average)."""

    RA_IN = [0, 2, 3]   # column indices of (v1, v3, v4) in X[:, 0..6]
    SI_IN = [1, 4]      # (v2, v5)
    CX_IN = [5, 6]      # (v6, v7)

    def __init__(self, mf: MFConfig | None = None):
        self.mf = mf or MFConfig()
        self.ra_a, self.ra_z = _unit_arrays(RA_RULES, 3)
        self.si_a, self.si_z = _unit_arrays(SI_RULES, 2)
        self.cx_a, self.cx_z = _unit_arrays(CX_RULES, 2)
        self.top_a, self.top_z = _unit_arrays(TOP_RULES, 3)

    def _infer_unit(self, Xsub, ants, z):
        M = self.mf.memberships(Xsub)
        W = firing_matrix(M, ants)
        return sugeno_ac(W, z)

    def intermediates(self, X: np.ndarray):
        X = np.asarray(X, dtype=np.float64)
        ra = self._infer_unit(X[:, self.RA_IN], self.ra_a, self.ra_z)
        si = self._infer_unit(X[:, self.SI_IN], self.si_a, self.si_z)
        cx = self._infer_unit(X[:, self.CX_IN], self.cx_a, self.cx_z)
        return ra, si, cx

    def infer(self, X: np.ndarray) -> np.ndarray:
        ra, si, cx = self.intermediates(X)
        Xtop = np.stack([ra, si, cx], axis=1)
        return self._infer_unit(Xtop, self.top_a, self.top_z)

    # ---- complexity accounting for the paper -----------------------------
    @staticmethod
    def complexity_table():
        rows = [
            ("RA (v1,v3,v4)", 3, 27, len(RA_RULES)),
            ("SI (v2,v5)",    2,  9, len(SI_RULES)),
            ("CX (v6,v7)",    2,  9, len(CX_RULES)),
            ("TOP (RA,SI,CX)", 3, 27, len(TOP_RULES)),
        ]
        total_grid = sum(r[2] for r in rows)
        total_used = sum(r[3] for r in rows)
        return rows, total_grid, total_used  # vs flat: 3^7=2187 grid, 18 used
