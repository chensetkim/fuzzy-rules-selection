"""
hierarchy.py -- T-HFIS architecture: which inputs feed which unit
==================================================================
Replaces the flat 7-input Sugeno engine with a two-layer hierarchy whose
decomposition follows the attack taxonomy:

  Layer 1 (evidence aggregation, one sub-FIS per taxonomy branch)
    RA  Rank-trajectory Anomaly   inputs v1 (monotonicity violation),
                                         v3 (CUSUM drift / spike),
                                         v4 (rank-jump vs link-cost)
    SI  Signal Instability        inputs v2 (Trickle resets),
                                         v5 (residual sign-flip count)
    CX  Corroboration / Context   inputs v6 (mobility index, exculpatory),
                                         v7 (two-hop residual, inculpatory)

  Layer 2 (decision)
    TOP inputs RA, SI, CX -> AC in [0,100]

All four units are zero-order Sugeno with the SAME machinery as the flat
engine (common/fuzzy.py): L/M/H sets on [0,100], min t-norm, singleton
consequents {0,25,50,75,100}. Intermediate outputs live on [0,100] and are
re-fuzzified with the same MF family.

Only the layout is defined here. Every rule in every unit is selected from
data by hfs_pipeline.py; no hand-crafted rules exist.

Complexity: complete grids 3^3+3^2+3^2+3^3 = 72 rules max vs 3^7 = 2187 flat.
"""

RA_IN = [0, 2, 3]   # column indices of (v1, v3, v4) in X[:, 0..6]
SI_IN = [1, 4]      # (v2, v5)
CX_IN = [5, 6]      # (v6, v7)

UNIT_INPUT_NAMES = {
    "RA": ["v1", "v3", "v4"],
    "SI": ["v2", "v5"],
    "CX": ["v6", "v7"],
    "TOP": ["RA", "SI", "CX"],
}
