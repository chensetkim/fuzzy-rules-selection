# CARS run summary — `run_2026-10-27_1503`

Seeds: 42

Settings: see `config.txt`.

| Split | Rules | F1 | FPR | Recall | Precision | Ceiling F1 |
|---|---|---|---|---|---|---|
| primary — knee | 16 | 0.8863 | 0.0053 | 0.8106 | 0.9775 | 0.9877 |
| primary — best-F1 | 21 | 0.9250 | 0.0202 | 0.9218 | 0.9282 | 0.9877 |
| round-holdout — knee | 13 | 0.7955 | 0.0053 | 0.6757 | 0.9669 | 0.9857 |
| round-holdout — best-F1 | 24 | 0.8880 | 0.0241 | 0.8828 | 0.8932 | 0.9857 |
| LOSO S1 — knee | 17 | 0.8198 | 0.0055 | 0.7044 | 0.9805 | 0.9937 |
| LOSO S2 — knee | 12 | 0.6849 | 0.0062 | 0.5314 | 0.9631 | 0.9933 |
| LOSO S3 — knee | 22 | 0.9851 | 0.0039 | 0.9812 | 0.9891 | 0.9995 |
| LOSO S4 — knee | 13 | 0.9259 | 0.0079 | 0.9001 | 0.9533 | 0.9997 |
| LOSO S5 — knee | 13 | 0.9334 | 0.0044 | 0.8935 | 0.9771 | 1.0000 |
| LOSO S6 — knee | 13 | 0.6120 | 0.0040 | 0.4483 | 0.9642 | 0.9794 |

LOSO mean F1 over S1–S6: **0.8268**

Ceiling F1 = best F1 any classifier of v1..v7 can reach on that test set (identical vectors carry both labels). A result at or near it suggests leakage rather than a better rule base.

Deployable rule bases: `seed_<s>/primary/selected_rules.c` (knee) and `selected_rules_best_f1.c` (best-F1). The firmware membership functions must match `MF_HIGH` in `config.txt`.
