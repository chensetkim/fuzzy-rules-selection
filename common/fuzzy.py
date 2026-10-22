"""
fuzzy.py -- Fuzzy core faithful to fuzzrid-fuzzy.c
====================================================
Membership functions, rule encoding, vectorised firing strengths, and
Sugeno weighted-average defuzzification, matching the on-device integer
implementation (Algorithm 2) so that offline rule selection evaluates
exactly the inference the Z1/MSP430 firmware will run.

Rule encoding
-------------
A rule is (antecedent, z):
  antecedent : tuple of 7 ints, one per feature v1..v7
               0 = don't care, 1 = Low, 2 = Medium, 3 = High
  z          : singleton consequent in {0, 25, 50, 75, 100}
Firing strength = min t-norm over the specified (non-zero) terms.
"""

from __future__ import annotations
import numpy as np

N_FEATURES = 7
DONT_CARE, LOW, MED, HIGH = 0, 1, 2, 3
TERM_NAMES = {0: "-", 1: "L", 2: "M", 3: "H"}
Z_LEVELS = np.array([0, 25, 50, 75, 100])
Z_NAMES = {0: "VL", 25: "L", 50: "M", 75: "H", 100: "VH"}

# ---------------------------------------------------------------------------
# Membership functions on [0,100] percent scale.
# Defaults follow the March-2026 firmware update: High shifted [50,80]->[60,90].
# Breakpoints are parameters so the pre-update base can be reproduced.
# ---------------------------------------------------------------------------

class MFConfig:
    def __init__(self,
                 low=(20, 50),      # mu_L = 1 for v<=20, linear -> 0 at 50
                 med=(20, 50, 80),  # mu_M = 0 at 20, peak 1 at 50, 0 at 80
                 high=(60, 90)):    # mu_H = 0 at 60, linear -> 1 at 90, 1 after
        self.low, self.med, self.high = low, med, high

    def memberships(self, X: np.ndarray) -> np.ndarray:
        """X: (n_samples, 7) feature matrix in [0,100].
        Returns M: (n_samples, 7, 3) with M[..., 0]=mu_L, 1=mu_M, 2=mu_H,
        each in [0,1]."""
        X = np.asarray(X, dtype=np.float64)
        a, b = self.low
        mu_l = np.clip((b - X) / (b - a), 0.0, 1.0)
        p, q, r = self.med
        mu_m = np.clip(np.minimum((X - p) / (q - p), (r - X) / (r - q)), 0.0, 1.0)
        c, d = self.high
        mu_h = np.clip((X - c) / (d - c), 0.0, 1.0)
        return np.stack([mu_l, mu_m, mu_h], axis=-1)


def firing_matrix(M: np.ndarray, antecedents: np.ndarray) -> np.ndarray:
    """Compute W (n_samples, n_rules): min t-norm firing strength of every
    rule on every sample.

    M           : (n_samples, 7, 3) membership tensor from MFConfig.memberships
    antecedents : (n_rules, 7) int array with entries in {0,1,2,3}
    """
    n_samples = M.shape[0]
    n_rules = antecedents.shape[0]
    W = np.empty((n_samples, n_rules), dtype=np.float64)
    for r in range(n_rules):
        ant = antecedents[r]
        mask = ant != DONT_CARE
        if not mask.any():
            W[:, r] = 0.0
            continue
        # M[:, feature_idx, term_idx-1] for each specified term
        feats = np.nonzero(mask)[0]
        terms = ant[feats] - 1
        W[:, r] = M[:, feats, terms].min(axis=1)
    return W


def sugeno_ac(W: np.ndarray, z: np.ndarray, subset=None, eps: float = 0.01) -> np.ndarray:
    """AC = sum(w_i z_i) / (sum(w_i) + eps) over the selected rule subset.

    eps = 0.01 mirrors the firmware's epsilon=1 on the 0..100 integer weight
    scale (weights here are in [0,1])."""
    if subset is not None:
        W = W[:, subset]
        z = z[subset]
    num = W @ z
    den = W.sum(axis=1) + eps
    return num / den


# ---------------------------------------------------------------------------
# Canonical expert rule base R1-R18 (fuzzrid-fuzzy.c, release-1.3 rev 2.0+)
# ---------------------------------------------------------------------------
# antecedent index:      v1  v2  v3  v4  v5  v6  v7
EXPERT_RULES = [
    # (name, antecedent, z)
    ("R1",  (HIGH, 0,    0,    0,    0,    0,    0), 100),  # v1 H -> VH
    ("R2",  (0,    0,    0,    0,    0,    0, HIGH), 100),  # v7 H -> VH
    ("R3",  (0,    0,    0, HIGH,    0,  LOW,    0),  75),  # v4 H & v6 L -> H
    ("R4",  (0, HIGH,    0, HIGH,    0,    0,    0), 100),  # v4 H & v2 H -> VH
    ("R5",  (0, HIGH,    0,  MED,    0,  LOW,    0),  75),  # v4 M & v2 H & v6 L
    ("R6",  (0,    0, HIGH,    0,    0,  LOW,    0),  75),  # v3 H & v6 L -> H
    ("R7",  (0, HIGH, HIGH,    0,    0,    0,    0), 100),  # v3 H & v2 H -> VH
    ("R8",  (0, HIGH,  MED,    0,    0,  LOW,    0),  75),  # v3 M & v2 H & v6 L
    ("R9",  (0,    0,    0,    0, HIGH,  LOW,    0),  75),  # v5 H & v6 L -> H
    ("R10", (0, HIGH,    0,    0, HIGH,    0,    0), 100),  # v5 H & v2 H -> VH
    ("R11", (0, HIGH,    0,    0,  MED,  LOW,    0),  75),  # v5 M & v2 H & v6 L
    ("R12", (0,  MED,    0,  MED,    0, HIGH,    0),  50),  # v6 H & v2 M & v4 M
    ("R13", (LOW,  0,    0,  LOW,    0, HIGH,    0),  25),  # v6 H & v1 L & v4 L
    ("R14", (0,  LOW,  LOW,  LOW,  LOW,    0,  LOW),   0),  # all-clear (incl v7)
    ("R15", (HIGH, 0,    0,    0,    0,    0, HIGH), 100),  # v1 H & v7 H -> VH
    ("R16", (0,    0, HIGH,    0,    0,    0, HIGH), 100),  # v3 H & v7 H -> VH
    ("R17", (0,    0, HIGH,    0, HIGH,    0,    0),  75),  # v3 H & v5 H -> H
    ("R18", (LOW,  0,  LOW,    0,    0, HIGH,    0),   0),  # exonerate mobile
]


def expert_arrays():
    ants = np.array([a for _, a, _ in EXPERT_RULES], dtype=np.int8)
    z = np.array([c for _, _, c in EXPERT_RULES], dtype=np.float64)
    names = [n for n, _, _ in EXPERT_RULES]
    return ants, z, names


def rule_str(ant, z) -> str:
    terms = [f"v{i+1} is {TERM_NAMES[t]}" for i, t in enumerate(ant) if t != DONT_CARE]
    return "IF " + " AND ".join(terms) + f" THEN AC = {Z_NAMES[int(z)]} ({int(z)})"
