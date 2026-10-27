# Historical record recovery

Prepared 27 October 2026. Searches were read-only; no Git history was rewritten.

## Recovered implementation record

Firmware repository: `DM-2H-FuzzRID-Contiki-OS-3.0`.
Commit: `0363d4605dfbd8998366f73c7c21827a0643da0f`.
Author and committer date recorded by Git: 2 September 2026, 14:09:30 +07:00.
Path: `apps/2h-fuzzrid/fuzzrid-fuzzy.c`.

The exported committed source is `firmware_0363d4605dfbd8998366f73c7c21827a0643da0f.c`. Its SHA-256 is `7d61c5d18d172fe2403a28dc970530049397e8fd48c90e14c02766849b9699c6`, identical to the entire current source file. The separate 33/33 source comparison therefore also applies to this recovered committed source. `firmware_history.csv` records this result.

This identifies an existing committed implementation of the fixed 33 rules. Git dates are repository metadata and are not independently authenticated timestamps. The commit alone does not establish when final experiments ran, which binary they used, or whether rule selection preceded all evaluation and tuning.

## Selection-history search

All 35 commits reachable through the selection repository's available refs were scanned. Saved `selected_rules*.txt` files yielded 79 distinct path/blob combinations. None matched the complete supplied 33-rule set. Details are in `committed_selection_inventory.csv`. This scope does not include unreachable Git objects, unavailable branches/remotes, external backups, or another computer.

The available narrative `reports/rules-selection-for-FERMAD.md`, section 15, describes a superseded plan injecting a 33-rule seed base into the candidate pool/population. That is a narrative description of a plan, not a recovered execution log proving that optimisation generated or retained all 33 rules. It must not be used to fill missing execution settings.

## Generated fixed-rule record

`../fixed_33_rulebase.json` is a new machine-readable extraction of the supplied fixed rules, tied to the recovered firmware commit and current rule correspondence. It preserves all 33 rules. It is not labelled an original optimiser output and does not assert a recovered historical selection run.

## Reproduction

From the selection repository root:

```sh
python3 reports/reviewer-comment-R01/recover_history.py
```

The script exports committed firmware, Git logs and inventories. It does not change the fixed rules or run optimisation. Historical selection settings, partition membership, evaluation build/run mapping and freeze relative to final evaluation remain unresolved. R01 is not yet closed.
