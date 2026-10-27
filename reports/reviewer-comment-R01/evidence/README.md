# R01 evidence inspection — 27 October 2026

These are newly generated inspections of currently retained artifacts, not historical execution or freeze records. Reproduce from the repository root:

```sh
.venv/bin/python reports/reviewer-comment-R01/collect_evidence.py
```

## Findings

- `rule_correspondence.csv`: all 33 numbered antecedents and singletons match the current firmware function `fuzzrid_fuzzy_r33_infer_ac_flat`. Conditions were parsed from the supplied list and C assignments; min/max expressions were translated to AND/OR. This is a source comparison, not a compiled firmware execution test. Source line numbers are included.
- `selection_output_inventory.csv`: 40 retained selected-rule text files were inspected, including legacy, full, and quick outputs. None is the complete supplied 33-rule set. This does not exclude an unlocated historical artifact elsewhere.
- `retained_config.txt`, `retained_SUMMARY.md`, `retained_select.log`: copies of the retained full seed-42 run. Primary knee/best-F1 outputs have 14/23 rules; round-holdout outputs have 16/31. These settings and results cannot be attributed to the deployed 33 rules.
- `development_counts.csv`: current loader/split reconstruction gives 390,201 events: 85,644 attack and 304,557 benign. Primary train/test sizes are 273,138/117,063, agreeing with the retained selection log. Class counts and round-holdout counts are new calculations, not recovered historical manifests.
- `allocation_manifest.csv` and `split_separation_check.json`: membership is expressed as scenario/environment/round/attacker-count groups because the loader does not retain source filenames. All 72 groups overlap in the primary split; zero overlap in round-holdout. These are group identities, not verified simulation seeds or shared-trace identities. Zero group overlap does not establish trace independence.
- `real_data.py.snapshot.txt`: primary partitioning shuffles individual event indices within each scenario; it does not keep complete runs together. No third, separately allocated development-validation partition is supplied by the inspected selection program.
- `finalize_selection.py.snapshot.txt`: `pick_best` selects using `f1_test`, with a 0.002 tolerance favoring fewer rules. Consequently that test partition participates in best-F1 model choice and cannot also be presented as an untouched final evaluation for that choice. Round-holdout finalization uses the same policy.
- `optimize.py.snapshot.txt`: current code uses uniform crossover probability 0.9, bit-flip mutation probability 1.0 with per-bit probability 1/pool-size, duplicate elimination, and random sparse initialization density 0.02. These are current source settings, not proof of the source used by a historical 33-rule selection.
- Retained full-run configuration records support 0.005, confidence margin 0.15, AC threshold 65, population 150, generations 250, optimiser seed 42, rule bounds 12–35, max antecedent terms 4, High membership 50/80, integer arithmetic, and launch-based labeling. The retained primary log records 3,990 enumerated plus 200 Wang–Mendel candidates, with 743 remaining after pruning. Do not describe these as the verified settings that produced the 33 rules.

## Inference checks and limits

Direct source inspection found Low trapezoid (0,0,20,50), Medium triangle (20,50,80), High trapezoid (50,80,100,100), not-High = 100 - High, integer division, and aggregation denominator initialized to 1 with a 33-rule accumulation loop. The dispatcher selects this function when WITH_THFIS=0. This does not identify the build flag or binary used for previously reported results. The membership and dispatcher source is identified by the firmware hash in `artifact_hashes.csv`; it is not independently exercised by this script.

## Provenance and remaining evidence

`artifact_hashes.csv` records present-day SHA-256 hashes of inspected sources, saved rule listings, retained full-run records, and current processed inputs/labeling inputs. Hashes identify current bytes; timestamps and recorded commit labels do not prove a pre-evaluation freeze. Source snapshots preserve the selection behavior inspected here.

Still needed: original 33-rule selection output and invocation/configuration; a corresponding historical data manifest; actual simulation seeds and trace-group identities; manuscript Table 9 comparison; historical source/build/run mapping; and retained configuration-freeze records. No performance claim for the 33-rule base has been established by this package. No optimisation or simulation was executed.
