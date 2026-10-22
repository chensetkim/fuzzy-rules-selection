"""
fuzzy.py -- Fuzzy core faithful to fuzzrid-fuzzy.c
====================================================
Membership functions, rule encoding, vectorised firing strengths, and
Sugeno weighted-average defuzzification.

Arithmetic (set_arithmetic):
  "int"   (default) exactly the on-device integer implementation (Algorithm 2):
          memberships are uint8 0..100 with truncating division
          ((v-a)*100/(b-a)), firing = integer min, AC = floor(sum w*z / (1 + sum w)).
          Offline selection then scores the inference the Z1/MSP430 runs.
  "float" the continuous model: memberships in [0,1], AC = sum w*z / (sum w + 0.01).

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

_INTEGER = True


def set_arithmetic(mode: str) -> None:
    """Select "int" (firmware-faithful, default) or "float" arithmetic for
    memberships() and sugeno_ac() everywhere."""
    global _INTEGER
    if mode not in ("int", "float"):
        raise ValueError(f"arithmetic must be 'int' or 'float', not {mode!r}")
    _INTEGER = mode == "int"


def integer_arithmetic() -> bool:
    return _INTEGER

N_FEATURES = 7
DONT_CARE, LOW, MED, HIGH = 0, 1, 2, 3
TERM_NAMES = {0: "-", 1: "L", 2: "M", 3: "H"}
Z_LEVELS = np.array([0, 25, 50, 75, 100])
Z_NAMES = {0: "VL", 25: "L", 50: "M", 75: "H", 100: "VH"}

# ---------------------------------------------------------------------------
# Membership functions on [0,100] percent scale.
# Defaults (2026-10-22): L = 1 on [0,20] -> 0 at 50; M = 0 at 20, peak at 50,
# 0 at 80; H = 0 at 50 -> 1 at 80, 1 on [80,100]. (The March-2026 firmware
# used High [60,90]; pass high=(60, 90) / --mf-high 60,90 to reproduce it.)
# Breakpoints are parameters so the pre-update base can be reproduced.
# ---------------------------------------------------------------------------

class MFConfig:
    def __init__(self,
                 low=(20, 50),      # mu_L = 1 for v<=20, linear -> 0 at 50
                 med=(20, 50, 80),  # mu_M = 0 at 20, peak 1 at 50, 0 at 80
                 high=(50, 80)):    # mu_H = 0 at 50, linear -> 1 at 80, 1 after
        self.low, self.med, self.high = low, med, high

    def memberships(self, X: np.ndarray) -> np.ndarray:
        """X: (n_samples, 7) feature matrix in [0,100].
        Returns M: (n_samples, 7, 3) with M[..., 0]=mu_L, 1=mu_M, 2=mu_H,
        each in [0,1]."""
        X = np.asarray(X, dtype=np.float64)
        if _INTEGER:
            return self._memberships_int(X)
        a, b = self.low
        mu_l = np.clip((b - X) / (b - a), 0.0, 1.0)
        p, q, r = self.med
        mu_m = np.clip(np.minimum((X - p) / (q - p), (r - X) / (r - q)), 0.0, 1.0)
        c, d = self.high
        mu_h = np.clip((X - c) / (d - c), 0.0, 1.0)
        return np.stack([mu_l, mu_m, mu_h], axis=-1)

    def _memberships_int(self, X: np.ndarray) -> np.ndarray:
        """trapezoidal_mf / triangular_mf of fuzzrid-fuzzy.c: inputs are uint8,
        each slope is (dist * 100) / width with truncating integer division.
        Returned as k/100 so firing_matrix (min) works unchanged."""
        V = np.rint(X).astype(np.int64)
        def ramp(dist, width):                     # 0..100, truncated
            return np.clip(np.floor_divide(dist * 100, width), 0, 100)
        a, b = self.low                            # 100 on [0,a], down to 0 at b
        mu_l = np.where(V <= a, 100, ramp(b - V, b - a))
        p, q, r = self.med                         # 0 at p, 100 at q, 0 at r
        mu_m = np.where(V <= q, ramp(V - p, q - p), ramp(r - V, r - q))
        c, d = self.high                           # 0 at c, up to 100 at d, 100 after
        mu_h = np.where(V >= d, 100, ramp(V - c, d - c))
        return np.stack([mu_l, mu_m, mu_h], axis=-1).astype(np.float64) / 100.0


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
    if _INTEGER:
        # Firmware: uint8 weights 0..100, num/den with den = 1 + sum(w), floor.
        Wi = np.rint(W * 100.0)
        return np.floor_divide(Wi @ np.asarray(z, dtype=np.float64), Wi.sum(axis=1) + 1.0)
    num = W @ z
    den = W.sum(axis=1) + eps
    return num / den


def rule_str(ant, z) -> str:
    terms = [f"v{i+1} is {TERM_NAMES[t]}" for i, t in enumerate(ant) if t != DONT_CARE]
    return "IF " + " AND ".join(terms) + f" THEN AC = {Z_NAMES[int(z)]} ({int(z)})"
