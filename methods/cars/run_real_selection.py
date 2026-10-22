#!/usr/bin/env python3
"""
run_real_selection.py -- Flat NSGA-II rule selection on the real data/processed corpus
==================================================================================
Wraps the existing candidates.py / optimize.py / report.py machinery around
common/real_data.py (which understands the real mobile+static / r1-r3 / 3-6-9
attacker-count layout, dedupes the byte-identical static repetitions, and
labels every event).

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
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "common"))

from fuzzy import set_arithmetic, MFConfig, firing_matrix, sugeno_ac
from candidates import build_pool
from optimize import run_nsga2, knee_solution, f1_fpr
from report import pareto_table, rules_listing, export_c
from real_data import (load_real_events, compress, vector_ceiling, stratified_scenario_split,
                       round_holdout_split, stratified_subsample)


def run_one(tag, ev_train, ev_test, out_dir, mf, args, note=""):
    os.makedirs(out_dir, exist_ok=True)
    # train-sample <= 0: use the whole training partition (weighted rows keep it cheap)
    train_sample = (stratified_subsample(ev_train, n_target=args.train_sample, seed=args.seed)
                    if args.train_sample > 0 else ev_train)
    # Identical (vector, label) events -> one weighted row; lossless (real_data.compress).
    X_trs, y_trs, w_trs = compress(train_sample)
    X_te, y_te, w_te = compress(ev_test)
    c_f1, c_fpr = vector_ceiling(ev_test)
    print(f"\n=== [{tag}] train={len(ev_train)} (used {len(train_sample)} events = "
          f"{len(y_trs)} weighted rows for pool/NSGA-II) test={len(ev_test)} "
          f"({len(y_te)} weighted rows) ===")
    print(f"[{tag}] data ceiling on this test: F1<={c_f1:.4f} (FPR {c_fpr:.4f})")

    pool = build_pool(X_trs, y_trs, mf, max_terms=args.max_terms,
                      min_support=args.min_support, conf_margin=args.conf_margin, w=w_trs)

    M_te = mf.memberships(X_te)
    W_te = firing_matrix(M_te, pool["antecedents"])

    masks, F = run_nsga2(pool, y_trs, ac_thr=args.ac_thr, max_rules=args.max_rules,
                         min_rules=args.min_rules, pop_size=args.pop,
                         n_gen=args.gens, seed=args.seed, w=w_trs)
    print(f"[{tag}] Pareto front: {len(masks)} non-dominated rule bases")

    tab = pareto_table(masks, F, pool, y_trs, W_te, y_te, args.ac_thr, pool["names"],
                       w_tr=w_trs, w_te=w_te)
    tab.to_csv(os.path.join(out_dir, "pareto_front.csv"), index=False)

    k = knee_solution(F)
    best = masks[k]
    ac_best = sugeno_ac(W_te, pool["z"], subset=best)
    f1_b, fpr_b, cm_b = f1_fpr(ac_best, y_te, args.ac_thr, w_te)
    with open(os.path.join(out_dir, "selected_rules.txt"), "w") as f:
        f.write(f"{note}\nKnee-point rule base ({int(best.sum())} rules)\n"
                f"test F1={f1_b:.4f} FPR={fpr_b:.4f} "
                f"recall={cm_b['recall']:.4f} precision={cm_b['precision']:.4f}\n"
                f"data ceiling on this test: F1<={c_f1:.4f} FPR={c_fpr:.4f}\n\n"
                + rules_listing(best, pool) + "\n")
    export_c(best, pool, os.path.join(out_dir, "selected_rules.c"))

    print(f"[{tag}] knee base: {int(best.sum())} rules | test F1={f1_b:.4f} "
          f"FPR={fpr_b:.4f}")
    return dict(tag=tag, pool=pool, best=best, f1=f1_b, fpr=fpr_b, cm=cm_b,
               n_rules=int(best.sum()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-root", default="data/processed")
    ap.add_argument("--out-root", default="outputs/cars")
    ap.add_argument("--ac-thr", type=float, default=65.0)
    ap.add_argument("--max-terms", type=int, default=4)
    ap.add_argument("--max-rules", type=int, default=35)
    ap.add_argument("--min-rules", type=int, default=12)
    ap.add_argument("--min-support", type=float, default=0.005)
    ap.add_argument("--conf-margin", type=float, default=0.15)
    ap.add_argument("--pop", type=int, default=150)
    ap.add_argument("--gens", type=int, default=250)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--test-frac", type=float, default=0.3)
    ap.add_argument("--train-sample", type=int, default=0,
                    help="events sampled for pool/NSGA-II; 0 = whole training partition")
    ap.add_argument("--mf-high", type=str, default="50,80")
    ap.add_argument("--arith", choices=["int", "float"], default="int",
                    help="int = firmware integer arithmetic (default), float = continuous model")
    ap.add_argument("--label-start", default="launch",
                    help="attack start for labelling: launch (each attacker\'s [ATK-LAUNCHED] time) or seconds, e.g. 300")
    args = ap.parse_args()
    set_arithmetic(args.arith)

    hc, hd = (int(x) for x in args.mf_high.split(","))
    mf = MFConfig(high=(hc, hd))

    ev = load_real_events(args.csv_root, label_start=args.label_start)

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
          f"FPR={primary['fpr']:.4f}")
    print(f"round-holdout: {holdout['n_rules']:2d} rules | unseen-round F1={holdout['f1']:.4f} "
          f"FPR={holdout['fpr']:.4f}")
    gap = primary['f1'] - holdout['f1']
    print(f"F1 gap (primary test vs unseen-round holdout): {gap:+.4f} "
          f"{'(small -> low overfit risk)' if abs(gap) < 0.05 else '(check for overfitting)'}")


if __name__ == "__main__":
    main()
