# Response to reviewer R01 — FERMAD 33-rule fuzzy system

Prepared: 27 October 2026

Status: Draft for author review. R01 remains open pending selection and evaluation evidence.

## Reviewer concern

“Offline selection and independent evaluation are asserted but not reproducibly specified.”

The concern above is reproduced from `R01-response-guide.txt`; the original reviewer document was not available in this folder.

## Proposed response

We thank the reviewer for identifying the incomplete specification of offline rule selection and evaluation separation. We agree that specifying the final classifier alone does not establish how its rules were selected or whether the final evaluation was independent of development.

For FERMAD, the author identifies the applied classifier as the flat 33-rule fuzzy system documented in the accompanying `applied-33-fuzzy-rules.txt`. That file lists all 33 antecedents and consequent singletons, the seven input definitions, membership functions, and inference operations. It identifies the implementation as `fuzzrid_fuzzy_r33_infer_ac_flat()` under `WITH_THFIS=0`. The description therefore concerns this flat rule base; the hierarchical inference path requires a separate specification.

The documented inputs are rank monotonicity violation, rank residual/plausibility anomaly, sustained CUSUM drift, rank jump, rank oscillation, mobility index, and two-hop parent-rank mismatch. Inputs and membership degrees use integer scales from 0 to 100. Low and High memberships use trapezoidal parameters (0, 0, 20, 50) and (50, 80, 100, 100), respectively, and Medium uses triangular parameters (20, 50, 80). A not-High condition is evaluated as 100 minus the High membership. Conjunction uses minimum and disjunction uses maximum; an input omitted from a rule imposes no constraint.

Each rule assigns a zero-order Sugeno singleton from the stated scale {0, 25, 50, 75, 100}. In the supplied 33-rule list, the singletons actually used are 0, 50, 75, and 100. With firing strengths w_r and singletons z_r, the documented output is

    AC = min(100, floor(sum(r=1..33, w_r * z_r) / (1 + sum(r=1..33, w_r))))

Membership calculations also use integer division. If no rule fires, AC is zero. A consequent singleton of 100 is therefore distinct from a final aggregated output of 100. This inference specification does not supply the separate classification threshold requested by the reviewer.

Several details are necessary to preserve the supplied rule base exactly. Rule 15 is Medium rank oscillation AND not-High mobility, with singleton 50. Rule 24 assigns singleton zero when mobility is High and monotonicity violation, CUSUM drift, and two-hop mismatch are Low; it contributes firing weight to the denominator. Rules 31 and 32 each contain one OR antecedent combining Medium and High membership of the corroborating input. Each must remain one rule because splitting either into two rules can change the weighted average. Rule 33 depends only on High two-hop mismatch and assigns singleton 100. The complete numbered specification is supplied in `applied-33-fuzzy-rules.txt`.

We inspected the currently available artifacts and supplied a new evidence package in `evidence/`. The rule-by-rule comparison in `rule_correspondence.csv` matches all 33 listed antecedents and singletons to the current firmware source. This establishes source correspondence, but does not identify the historical binary used for the reported results. The inventory of 40 saved selected-rule listings found no complete match to this 33-rule base. In particular, the retained full seed-42 selection run produced primary knee/best-F1 outputs with 14/23 rules and round-holdout outputs with 16/31 rules. We therefore cannot attribute the deployed 33 rules to that run.

The package includes retained configuration and selection logs, current source snapshots, newly reconstructed allocation and class counts, and present-day artifact hashes. The current primary split contains 273,138 training events (59,812 attack; 213,326 benign) and 117,063 test events (25,832 attack; 91,231 benign). All 72 scenario/environment/round/attacker-count groups occur on both sides because the implementation partitions events within scenarios. The round-holdout reconstruction contains 294,308 training events and 95,893 test events, with no overlap in those group identities; shared movement and attack-trace independence remains unverified. These reconstructed partitions belong to the inspected selection pipeline and are not established as the historical partitions that produced the 33 rules.

The current finalization code also uses test-set F1 to choose the best-F1 rule base. That partition therefore participates in model selection and cannot be described as an untouched final evaluation for the selected output. The retained configuration and optimiser settings are documented in `evidence/README.md`, with their source records, but are not asserted to have produced the 33-rule base. We additionally recovered firmware commit `0363d4605dfbd8998366f73c7c21827a0643da0f`, whose recorded author and committer date is 2 September 2026. Its entire fuzzy source file is byte-identical to the current source matched against the 33 rules. The exported source, commit metadata, and historical listing inventory are supplied in `evidence/history/`. Across all 35 reachable selection-repository commits, 79 distinct saved rule-listing path/blob combinations contained no exact 33-rule match. This recovers a committed implementation record, but Git dates alone do not establish a freeze relative to final evaluation. The historical selection chain, trace separation, Table 9 correspondence, and evaluated build/run mapping remain unresolved. We leave R01 open pending those records and do not claim that current file hashes establish historical timing.

## Author completion notes — exclude from the submitted response

- Identify the actual selection invocation, configuration, inputs, and saved outputs. Executable defaults alone do not establish historical settings.
- Supply partition membership and attack/benign counts, distinguishing simulation seeds from the optimiser seed.
- Check run identities and shared movement/attack-trace groups across development and final evaluation.
- Recover configuration-freeze records where available; newly generated hashes cannot establish historical timing.
- Compare every selected antecedent and consequent with the supplied 33-rule list, Table 9, and the evaluated firmware. Include membership, rounding, aggregation, and classification settings.
- Add manuscript locations only after revisions are made. This draft does not assert that the manuscript has been revised.
- Revise the evidence-status paragraph when checks are completed. Report specific unavailable records if recovery fails; do not treat the present draft as closing R01.

Source basis: `applied-33-fuzzy-rules.txt`, `R01-response-guide.txt`, and the author's identification of the 33-rule list as the rules applied to FERMAD. A new source-to-rule comparison and current data-split reconstruction were performed; supporting artifacts are in `evidence/`. No simulations, optimiser replay, or historical provenance verification were performed.
