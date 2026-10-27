# FERMAD simulation execution plan for R01

Prepared: 27 October 2026 (Asia/Bangkok).
Status: Proposed campaign; no builds or simulations launched. Implements the direction in `data-regeneration-plan.md`.

## Purpose and scope

Generate a new, reproducible development corpus and a reserved final evaluation for the fixed 33-rule FERMAD system. Run a separately documented selection/reconstruction experiment against that reference. Exact recovery of all 33 rules is a comparison outcome, not a guaranteed result or an acceptance criterion for choosing simulation data.

Start with the existing training envelope: scenarios S1–S6, 3/6/9 attackers, static/mobile conditions and the 150-labelled training templates. Verify actual node counts, geometry, radio and mobility settings from XML and trace metadata before freezing the campaign; filenames alone are insufficient. Claims about other densities/areas require a separately specified extension.

## Existing entry points and problems to resolve

- Simulation templates: `/home/kimpc/Github/Simulation-phD-Project-01/ScriptGeneraeFile/FileTrain/{Static,Mobile}`.
- Existing launcher: `DM-FuZZ/auto_run_dm_fuzzrid.sh` in that repository. It currently reads `SimFiles/Mobile`, runs three rounds, uses Cooja seeds `123456 + round`, builds shared firmware, and writes a shared parameter file. It is a reference implementation, not the new campaign launcher.
- Existing build: `/home/kimpc/Github/DM-2H-FuzzRID-Contiki-OS-3.0/Simulation/build_exp5438_firmware.sh`. It deletes/replaces shared `examples/0-sim/*.exp5438` outputs and hardcodes several settings. Use a campaign-local source/build copy and adapt the build there.
- Existing logger: `DM-FuZZ/cooja_mote_output.js`. It reads the shared `script_paramter.txt`, opens logs for overwrite, and stops after 3,600,000 simulation milliseconds. Replace the shared dependency with a per-run logger/configuration and exclusive output creation.
- The inspected mobile template points to a fixed `.dat` movement file. Changing only the Cooja seed does not make that movement realization independent. Generate separate trace families and record their seeds and hashes.
- Firmware currently defines `FUZZRID_TAU_Q_PCT=55`, while the inspected selection run used AC threshold 65. Proposed new campaign uses 55 to match the fixed deployed source. Verify the actual AC comparison and any other decision thresholds, and explicitly pass 55 to offline evaluation. This is a new-campaign choice, not proof of the historical evaluation threshold. Do not assume an environment override changes an unconditional header definition.

## Proposed matrix and allocation

Use ten new realization families, allocated before generating outcomes:

| Partition | Families | Attacked runs | Attack-free runs | Total |
|---|---|---:|---:|---:|
| Candidate generation | 1–6 | 216 | 36 | 252 |
| Development validation | 7–8 | 72 | 12 | 84 |
| Final evaluation | 9–10 | 72 | 12 | 84 |
| Total | 1–10 | 360 | 60 | 420 |

Attacked runs per family: 6 scenarios × 3 attacker counts × 2 mobility conditions = 36. Attack-free controls per family: 3 corresponding network layouts × 2 conditions = 6, with the nominal attacker nodes configured as honest nodes. These control layouts are matched conditions, not three different attack counts in a benign network. Retain all eligible honest-source observations in controls; do not automatically drop nominal attacker IDs there.

Proposed seed namespaces: Cooja 270001–270010; movement 370001–370010; topology 470001–470010; attack timing/randomness 570001–570010 if that component supports independent seeding. Record actual supported mechanisms; an unused proposed seed is not evidence. Check namespaces against existing manifests before use and deterministically replace the entire proposed list if a collision is found.

A realization family may deliberately share topology/movement across attack variants for paired comparisons, but every dependent run must stay in its assigned partition. Record all shared-trace hashes and family dependencies. Shared deterministic attack schedules must be described explicitly; inspect whether they reuse random realizations across partitions. Static repetitions must differ in verified relevant random realizations; byte-identical data do not count as independent repetitions.

This matrix is an initial design, not a power calculation. Any changes based on pilot feasibility must be recorded before the full campaign and before final outcomes are inspected.

## Stage 1 — prepare an isolated campaign

Create a new directory under `Simulation-phD-Project-01/SimData/FERMAD-R01-new/` with `source/`, `firmware/`, `templates/`, `traces/`, `manifests/`, `runs/`, `processed/`, and `analysis/`. Do not overwrite existing evidence or raw data. Save Git commit IDs, patches/untracked build inputs, Java/Cooja/toolchain versions, and source/JAR hashes.

Implement a manifest-driven launcher with explicit preparation, pilot, development, and final stages. Preparation must validate file references, seeds, trace hashes, partition membership and unique output destinations without starting Cooja. Archive resolved XML and logging script for every run. Do not depend on global parameter files or mutable firmware paths.

Required manifest fields: campaign/run ID, partition, family/group ID, scenario, environment, actual node/root/attacker IDs, geometry, radio settings, Cooja seed, topology/movement/attack trace identities and seeds, timeout, build/configuration hashes, and resolved CSC hash. Include separate optimiser seeds later.

## Stage 2 — build and verify passive data collection

Keep `WITH_THFIS=0`, `WITH_FUZZRID=1`, `WITH_2HOP_TLV=1`, and the unchanged 33-rule inference. Author-confirmed requirement: build collection firmware with `FUZZRID_MONITOR_ONLY=1`. Set `ATK_WARNING_ENABLE=0` consistently across relevant builds to prevent warning-driven attacker feedback. Inspect all root/relay/attacker paths to verify that monitoring actually prevents warnings, isolation, route penalties and attack reset feedback. `FUZZRID_DETECT_ONLY=1` alone is insufficient: the existing build documents that warnings remain enabled.

The existing build script does not currently pass `FUZZRID_MONITOR_ONLY` and hardcodes warnings on. Its campaign-local replacement must pass the following explicit detector build definitions to both root and honest-node builds:

```text
WITH_FUZZRID=1
WITH_2HOP_TLV=1
WITH_THFIS=0
FUZZRID_MONITOR_ONLY=1
ATK_WARNING_ENABLE=0
```

Pass `ATK_WARNING_ENABLE=0` to all attacker builds as well. Record effective preprocessor definitions and binary hashes; setting a shell environment variable alone is insufficient with the present script. Source inspection confirms that `FUZZRID_MONITOR_ONLY=1` excludes the `fuzzrid_apply_amlm()` call while retaining feature and fuzzy inference computation. Verify other warning/report paths during the pilot.

Preserve the inspected attack setup initially: late stage, delta 20, 600-second warm-up, forge mode 0 and configured packet dropping, subject to verification against generated scenarios. Record scenario-specific behavior rather than assuming every attack uses every setting. Build root, honest node and attackers S1–S6; archive compiler commands, effective preprocessor settings, binary hashes and sizes. Build a separate attack-free node configuration for controls.

Selection data and passive fixed-rule classification can use this collection arm. Any claim about the operational warning/mitigation system needs a separate operational arm, fresh or paired appropriately, with its settings and outcomes reported separately. Do not infer network-level mitigation benefit from offline classification.

## Stage 3 — pilot, excluded from evidence partitions

Use four additional seed/trace families outside 1–10 for static S1, mobile S1, mobile S6 and an attack-free control. Pilot 300 simulated seconds for loading/logging and then complete 3,600 simulated seconds, since attacks start no earlier than the configured 600-second warm-up. The short check cannot verify attacks.

Confirm: correct firmware and flat dispatcher; advancing simulation timestamps; expected node count; routing/traffic activity; attack-launch markers and attacker IDs; v1–v7/AC logging; no unintended warning/reset/enforcement; correct log time units; normal completion marker; no fatal exception or stalled mote. Compare offline 33-rule AC with logged AC on pilot events, including integer rounding. Record discrepancies before proceeding.

Measure wall time, peak memory and log size. Start sequentially. Choose concurrency only after verifying independent outputs and measured resource capacity. Never estimate wall duration from simulated duration alone. Budget approximately 420 × measured representative run time / validated concurrency, plus build, analysis and retries; report static/mobile estimates separately.

## Stage 4 — execute development batches

Run candidate families 1–6 and validation families 7–8 using the frozen manifest. Save serial output, launcher stdout/stderr, exit status, start/end times, effective inputs and completion checks for each run. Resume only incomplete runs; keep failed logs and use distinct attempt IDs. Define failure criteria before analysis: process failure, missing expected end time, fatal simulation exception, or unusable logs. Do not discard successful low-performance runs. Retain the first technically valid attempt under the declared policy.

Parse into campaign-local CSVs. Use the existing parser and attack-launch extractor as starting points; verify their CLI and time units before execution. Label attack observations using actual launch markers. Record honest-source samples and attacker-observer/pre-launch exclusions, including the different control treatment. Produce counts by run, class, scenario, environment and partition. Check duplicate inputs/outputs and shared-trace overlap before selection.

## Stage 5 — selection and reference comparison

Adapt the selection program to read the manifest's explicit candidate/validation allocation. Do not use the current event-level primary split or test-score finalization as final-evaluation logic. Implement and verify support for not-High and single-rule OR conditions before claiming reference coverage.

Proposed search budget: population 150, 250 generations, support 0.005, confidence margin 0.15, optimiser seeds 1–5, integer arithmetic, AC threshold 55. Keep bounds 12–35 for an unconstrained comparison. An additional exactly-33-rule reconstruction may use bounds 33–33, but count alone does not establish reference equivalence. Disclose any reference injection or hand-specified antecedents. Freeze the final search policy and settings before running the full search; save their precise interpretation and implementation.

Select using development validation only under a declared ranking/tie-break rule. Preserve every candidate/pruning/Pareto/selected output and compare all antecedents, singletons and inference settings to the fixed reference. No change to data or seed choice may be justified by wanting an exact match. If the output differs, report it and retain the fixed 33-rule system as a separately evaluated reference.

## Stage 6 — freeze and final evaluation

Before starting final families 9–10, archive the rule/configuration/build hashes, offline evaluator, chosen policy, and a dated freeze record. Keep final outputs unavailable to selection/tuning. Evaluate the fixed reference and any declared selected comparator on the same reserved passive observations where appropriate. This is a new freeze record, not retrospective evidence about old experiments.

Report per-run confusion counts, precision, recall, F1, FPR and no-rule-firing rates, with pooled counts and uncertainty reflecting independent realization families. Two final families provide limited uncertainty estimation; report that limitation rather than treating individual events as independent replicates. Include benign-only FPR and stratification by scenario/environment/attacker count. Detection latency or network effects require their own predeclared definitions and appropriate operational runs.

## Deliverables and completion

Deliver campaign/source/build manifests, resolved inputs and hashes, complete run logs/status records, processed data and class counts, separation checks, selection/reconstruction artifacts, fixed-rule comparison, freeze record, and final evaluation report. Link every reported result to run/build identities and update R01 using explicitly new-experiment language.

Next implementation step: prepare the campaign manifest, isolated build/logger and dry-run launcher; then execute the excluded pilot. No simulation command for that new launcher is provided here because it has not yet been implemented. The existing global batch runner must not be presented as if it already satisfies this plan.
