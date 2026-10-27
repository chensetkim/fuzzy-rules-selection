# CARS run summary — `run_2026-10-27_1217_quick`

Seeds: 42

Settings: see `config.txt`.

| Split | Rules | F1 | FPR | Recall | Precision | Ceiling F1 |
|---|---|---|---|---|---|---|
| primary — knee | 23 | 0.8324 | 0.0100 | 0.7380 | 0.9544 | 0.9877 |
| primary — best-F1 | 20 | 0.8980 | 0.0359 | 0.9180 | 0.8788 | 0.9877 |
| round-holdout — knee | 13 | 0.7328 | 0.0037 | 0.5877 | 0.9731 | 0.9857 |
| round-holdout — best-F1 | 13 | 0.8585 | 0.0411 | 0.8873 | 0.8316 | 0.9857 |
| LOSO S1 — knee | 18 | 0.8172 | 0.0242 | 0.7335 | 0.9224 | 0.9937 |
| LOSO S2 — knee | 15 | 0.6880 | 0.0068 | 0.5361 | 0.9601 | 0.9933 |
| LOSO S3 — knee | 17 | 0.8253 | 0.0040 | 0.7105 | 0.9844 | 0.9995 |
| LOSO S4 — knee | 17 | 0.8509 | 0.0358 | 0.8881 | 0.8167 | 0.9997 |
| LOSO S5 — knee | 20 | 0.9530 | 0.0122 | 0.9636 | 0.9426 | 1.0000 |
| LOSO S6 — knee | 13 | 0.5245 | 0.0194 | 0.3843 | 0.8259 | 0.9794 |

LOSO mean F1 over S1–S6: **0.7765**

Ceiling F1 = best F1 any classifier of v1..v7 can reach on that test set (identical vectors carry both labels). A result at or near it suggests leakage rather than a better rule base.

Deployable rule bases: `seed_<s>/primary/selected_rules.c` (knee) and `selected_rules_best_f1.c` (best-F1). The firmware membership functions must match `MF_HIGH` in `config.txt`.
