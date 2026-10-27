# FERMAD data regeneration and 33-rule reconstruction plan

Recorded: 27 October 2026

Status: Plan recorded; data regeneration, optimisation, and final evaluation have not started.

## Objective

Regenerate documented simulation data and run the rule-selection pipeline, comparing its output with the fixed reference in `applied-33-fuzzy-rules.txt`. Preserve the existing evidence and historical artifacts.

An exact-match requirement makes this a reconstruction task. Independent rule selection may produce a different rule base. New experiments provide new evidence; they do not recover the original selection history.

## Planned work

1. Freeze the reference: preserve all 33 antecedents and singletons, membership functions, integer arithmetic, and aggregation. Identify and explicitly freeze the classification threshold before evaluation; do not infer the historical threshold from an unrelated selection run. Record versions and hashes.
2. Regenerate development data: retain simulator and source versions, invocation/configuration, simulation seeds, mobility and attack-trace identities, labeling rules, and sample/class counts. Author-confirmed collection requirement: build firmware with `FUZZRID_MONITOR_ONLY=1`; record effective build definitions and verify no enforcement. Disable warnings consistently to prevent attacker feedback, as detailed in `simulation-run-plan.md`.
3. Allocate three partitions before selection: candidate generation, development validation, and final evaluation. Keep complete runs and shared movement/attack-trace groups together. Record membership and check overlap. Reserve final evaluation from all tuning and selection.
4. Check candidate coverage: confirm that the generator can represent every reference rule, including not-High conditions, the OR antecedents in rules 31–32 as single rules, and unconstrained inputs. Record unsupported structures and any necessary implementation changes.
5. Run selection and compare: retain the candidate pool, pruning decisions, support/confidence settings, rule-count bounds, optimiser configuration, random seeds, logs, Pareto outputs, and selected rules. Produce a rule-by-rule comparison with the reference. Report differences rather than silently changing the reference or selection procedure.
6. Freeze the selected configuration using development validation, then evaluate it once on the reserved final partition. Link outputs to source/build/configuration identities and preserve the freeze record before that evaluation.

## Exact preservation route

If all 33 reference rules must be preserved exactly, evaluate the fixed 33-rule system directly and describe the new experiment as validation of a fixed system. A selection experiment deliberately constrained or tuned to reproduce the reference must be reported as reconstruction, with the constraints and tuning disclosed. It is not evidence of independent discovery of those rules.

## Evidence and response

Keep regenerated data and new outputs separate from recovered historical records. Supply allocation and class-count manifests, run/trace separation checks, exact invocations, configuration/source hashes, candidate and selected-rule artifacts, rule correspondence, and evaluation records. Revise the R01 response to identify the new work and its actual findings. Do not claim that the new run establishes the original derivation or retrospectively proves independence of previously reported results.

R01 remains open until the resulting evidence is reviewed against the reviewer request.
