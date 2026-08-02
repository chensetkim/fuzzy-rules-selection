#!/usr/bin/env python3
"""
run_real_selection.py -- Flat NSGA-II rule selection on the real Data/csv corpus
==================================================================================
Wraps the existing candidates.py / optimize.py / report.py machinery around
Data/real_data.py (which understands the real mobile+static / r1-r3 / 3-6-9
attacker-count layout, dedupes the byte-identical static repetitions, and
labels every event) instead of the single-atk_nodes CARS/rs/data.py loader.

Two runs are produced:

  1. PRIMARY  -- scenario-stratified 70/30 split (all six attack variants,
     every env/round/atkcount, on both sides). This is what's reported as
     the selected rule base.
  2. ROUND-HOLDOUT -- an independent re-run of the *entire* candidate
     generation + NSGA-II selection using only mobile r1+r2 and static r1
     as training data, then evaluated on mobile r3 -- a simulation
     repetition never touched during candidate generation, MF fitting, or
     selection. This is the overfitting check: if F1/FPR on this truly
     unseen round is close to the primary test-split numbers, the selected
     rules generalise rather than memorising one split.

Candidate-pool + NSGA-II fitness evaluation run on a stratified subsample of
the training rows (tractable candidate-firing-matrix size); final reported
metrics always use the FULL (non-subsampled) evaluation split.
"""
import argparse
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Data"))

from fuzzy import MFConfig, firing_matrix, expert_arrays, sugeno_ac
from candidates import build_pool
from optimize import run_nsga2, knee_solution, f1_fpr
from report import pareto_table, rules_listing, export_c, overlap_stats
from real_data import (load_real_events, features_labels, stratified_scenario_split,
                       round_holdout_split, stratified_subsample)


def run_one(tag, ev_train, ev_test, out_dir, mf, args, note=""):
    os.makedirs(out_dir, exist_ok=True)
    train_sample = stratified_subsample(ev_train, n_target=args.train_sample,
                                        seed=args.seed)
    print(f"\n=== [{tag}] train={len(ev_train)} (sampled {len(train_sample)} for "
          f"pool/NSGA-II) test={len(ev_test)} ===")
    X_trs, y_trs, _ = features_labels(train_sample)
    X_te, y_te, _ = features_labels(ev_test)

    pool = build_pool(X_trs, y_trs, mf, max_terms=args.max_terms,
                      min_support=args.min_support, conf_margin=args.conf_margin)

    e_ants, e_z, _ = expert_arrays()
    M_te = mf.memberships(X_te)
    W_te = firing_matrix(M_te, pool["antecedents"])
    exp_mask = pool["expert_mask"]
    ac_exp = sugeno_ac(W_te, pool["z"], subset=exp_mask)
    f1_e, fpr_e, cm_e = f1_fpr(ac_exp, y_te, args.ac_thr)
    print(f"[{tag}] expert R1-R18 on this test: F1={f1_e:.4f} FPR={fpr_e:.4f} "
          f"recall={cm_e['recall']:.4f} precision={cm_e['precision']:.4f}")

    masks, F = run_nsga2(pool, y_trs, ac_thr=args.ac_thr, max_rules=args.max_rules,
                         min_rules=args.min_rules, pop_size=args.pop,
                         n_gen=args.gens, seed=args.seed)
    print(f"[{tag}] Pareto front: {len(masks)} non-dominated rule bases")

    tab = pareto_table(masks, F, pool, y_trs, W_te, y_te, args.ac_thr, pool["names"])
    tab.to_csv(os.path.join(out_dir, "pareto_front.csv"), index=False)

    k = knee_solution(F)
    best = masks[k]
    ov = overlap_stats(best, exp_mask)
    ac_best = sugeno_ac(W_te, pool["z"], subset=best)
    f1_b, fpr_b, cm_b = f1_fpr(ac_best, y_te, args.ac_thr)
    with open(os.path.join(out_dir, "selected_rules.txt"), "w") as f:
        f.write(f"{note}\nKnee-point rule base ({int(best.sum())} rules)\n"
                f"test F1={f1_b:.4f} FPR={fpr_b:.4f} "
                f"recall={cm_b['recall']:.4f} precision={cm_b['precision']:.4f}\n"
                f"expert overlap: {ov['n_expert_in_base']}/18 expert rules kept, "
                f"Jaccard={ov['jaccard']:.3f}\n\n"
                + rules_listing(best, pool) + "\n")
    export_c(best, pool, os.path.join(out_dir, "selected_rules.c"))

    with open(os.path.join(out_dir, "overlap_report.txt"), "w") as f:
        f.write("base_id,n_rules,expert_in_base,jaccard,expert_coverage\n")
        for i, m in enumerate(masks):
            o = overlap_stats(m, exp_mask)
            f.write(f"{i},{o['n_selected']},{o['n_expert_in_base']},"
                    f"{o['jaccard']:.3f},{o['expert_coverage']:.3f}\n")

    print(f"[{tag}] knee base: {int(best.sum())} rules | test F1={f1_b:.4f} "
          f"FPR={fpr_b:.4f} | expert kept={ov['n_expert_in_base']}/18")
    return dict(tag=tag, pool=pool, best=best, f1=f1_b, fpr=fpr_b, cm=cm_b,
               n_rules=int(best.sum()), expert_f1=f1_e, expert_fpr=fpr_e)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-root", default="Data/csv")
    ap.add_argument("--out-root", default="CARS/rule_selection_real")
    ap.add_argument("--ac-thr", type=float, default=65.0)
    ap.add_argument("--max-terms", type=int, default=4)
    ap.add_argument("--max-rules", type=int, default=29)
    ap.add_argument("--min-rules", type=int, default=12)
    ap.add_argument("--min-support", type=float, default=0.005)
    ap.add_argument("--conf-margin", type=float, default=0.15)
    ap.add_argument("--pop", type=int, default=150)
    ap.add_argument("--gens", type=int, default=250)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--test-frac", type=float, default=0.3)
    ap.add_argument("--train-sample", type=int, default=40000)
    ap.add_argument("--mf-high", type=str, default="60,90")
    args = ap.parse_args()

    hc, hd = (int(x) for x in args.mf_high.split(","))
    mf = MFConfig(high=(hc, hd))

    ev = load_real_events(args.csv_root)

    # ---- Primary: scenario-stratified split -------------------------------
    tr, te = stratified_scenario_split(ev, test_frac=args.test_frac, seed=args.seed)
    primary = run_one("primary", tr, te, os.path.join(args.out_root, "primary"),
                      mf, args,
                      note="Scenario-stratified 70/30 split (all env/round/atkcount "
                           "pooled; all 6 attack variants on both sides).")

    # ---- Robustness: round-holdout (leave mobile-r3 out entirely) ---------
    trh, teh = round_holdout_split(ev, test_round="r3")
    holdout = run_one("round-holdout", trh, teh,
                      os.path.join(args.out_root, "round_holdout"), mf, args,
                      note="Independent re-selection trained on mobile r1+r2 + "
                           "static r1 only; evaluated on mobile r3, a simulation "
                           "repetition never used for candidate generation or "
                           "NSGA-II fitness. Tests generalisation, not deployed.")

    print("\n=== SUMMARY (flat) ===")
    print(f"primary:       {primary['n_rules']:2d} rules | test F1={primary['f1']:.4f} "
          f"FPR={primary['fpr']:.4f}  (expert F1={primary['expert_f1']:.4f})")
    print(f"round-holdout: {holdout['n_rules']:2d} rules | unseen-round F1={holdout['f1']:.4f} "
          f"FPR={holdout['fpr']:.4f}  (expert F1={holdout['expert_f1']:.4f})")
    gap = primary['f1'] - holdout['f1']
    print(f"F1 gap (primary test vs unseen-round holdout): {gap:+.4f} "
          f"{'(small -> low overfit risk)' if abs(gap) < 0.05 else '(check for overfitting)'}")


if __name__ == "__main__":
    main()
