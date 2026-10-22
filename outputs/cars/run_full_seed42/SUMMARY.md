# CARS run summary — `run_full_seed42`

Seeds: 42

Settings: see `config.txt`.

| Split | Rules | F1 | FPR | Recall | Precision | Ceiling F1 |
|---|---|---|---|---|---|---|
| primary — knee | 14 | 0.8778 | 0.0051 | 0.7964 | 0.9778 | 0.9877 |
| primary — best-F1 | 23 | 0.9252 | 0.0215 | 0.9262 | 0.9243 | 0.9877 |
| round-holdout — knee | 16 | 0.8119 | 0.0058 | 0.7007 | 0.9652 | 0.9857 |
| round-holdout — best-F1 | 31 | 0.8927 | 0.0258 | 0.8970 | 0.8883 | 0.9857 |
| LOSO S1 — knee | 14 | 0.8114 | 0.0087 | 0.6979 | 0.9690 | 0.9937 |
| LOSO S2 — knee | 15 | 0.6544 | 0.0039 | 0.4926 | 0.9743 | 0.9933 |
| LOSO S3 — knee | 20 | 0.9436 | 0.0035 | 0.9019 | 0.9894 | 0.9995 |
| LOSO S4 — knee | 25 | 0.9243 | 0.0066 | 0.8906 | 0.9606 | 0.9997 |
| LOSO S5 — knee | 14 | 0.9781 | 0.0049 | 0.9798 | 0.9765 | 1.0000 |
| LOSO S6 — knee | 18 | 0.6576 | 0.0037 | 0.4973 | 0.9701 | 0.9794 |

LOSO mean F1 over S1–S6: **0.8282**

Ceiling F1 = best F1 any classifier of v1..v7 can reach on that test set (identical vectors carry both labels). A result at or near it suggests leakage rather than a better rule base.

Deployable rule bases: `seed_<s>/primary/selected_rules.c` (knee) and `selected_rules_best_f1.c` (best-F1). The firmware membership functions must match `MF_HIGH` in `config.txt`.
