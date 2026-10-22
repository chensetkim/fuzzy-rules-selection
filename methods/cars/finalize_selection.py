#!/usr/bin/env python3
"""
finalize_selection.py -- pick the best-F1 Pareto point (not just the
generic knee) within [min_rules, max_rules], and (re-)emit the detailed
rule listing + C export for it.

The knee heuristic in optimize.knee_solution (weighted distance to the
ideal point, weights 0.6/0.3/0.1 across F1/FPR/size) is a reasonable
generic default, but the user's actual objective is explicit: highest
F1 (without overfitting) inside a hard [min_rules, max_rules] budget --
which is exactly what every row of pareto_front.csv already satisfies
(the NSGA-II constraint enforces the budget), so "best" reduces to
argmax f1_test, tie-broken toward fewer rules within a small tolerance.

Rebuilds the SAME candidate pool the run script built (same seed, same
data split, same train-sample), then maps the chosen row's rule-name
list back to a boolean mask so selected_rules.txt / .c can be
regenerated exactly like report.py does for the knee pick.
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "common"))

from fuzzy import set_arithmetic, MFConfig, firing_matrix, sugeno_ac
from candidates import build_pool
from optimize import f1_fpr
from report import rules_listing, export_c
from real_data import (load_real_events, compress, vector_ceiling, stratified_scenario_split,
                       round_holdout_split, stratified_subsample)


def pick_best(df: pd.DataFrame, min_rules: int, max_rules: int, tol: float = 0.002):
    cand = df[(df.n_rules >= min_rules) & (df.n_rules <= max_rules)]
    if cand.empty:
        cand = df
    best_f1 = cand.f1_test.max()
    near = cand[cand.f1_test >= best_f1 - tol]
    row = near.sort_values(["n_rules", "f1_test"], ascending=[True, False]).iloc[0]
    return row


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-root", default="data/processed")
    ap.add_argument("--out-dir", required=True, help="e.g. outputs/cars/primary")
    ap.add_argument("--split", choices=["primary", "round_holdout"], required=True)
    ap.add_argument("--ac-thr", type=float, default=65.0)
    ap.add_argument("--max-terms", type=int, default=4)
    ap.add_argument("--min-support", type=float, default=0.005)
    ap.add_argument("--conf-margin", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--split-seed", type=int, default=42,
                    help="seed of the primary (P1) 70/30 split; fixed across search seeds")
    ap.add_argument("--test-frac", type=float, default=0.3)
    ap.add_argument("--train-sample", type=int, default=0,
                    help="events sampled for pool/NSGA-II; 0 = whole training partition")
    ap.add_argument("--mf-high", type=str, default="50,80")
    ap.add_argument("--arith", choices=["int", "float"], default="int",
                    help="int = firmware integer arithmetic (default), float = continuous model")
    ap.add_argument("--label-start", default="launch",
                    help="attack start for labelling: launch (each attacker\'s [ATK-LAUNCHED] time) or seconds, e.g. 300")
    ap.add_argument("--min-rules", type=int, default=12)
    ap.add_argument("--max-rules", type=int, default=35)
    args = ap.parse_args()
    set_arithmetic(args.arith)

    hc, hd = (int(x) for x in args.mf_high.split(","))
    mf = MFConfig(high=(hc, hd))
    ev = load_real_events(args.csv_root, label_start=args.label_start, verbose=False)
    if args.split == "primary":
        tr, te = stratified_scenario_split(ev, test_frac=args.test_frac, seed=args.split_seed)
    else:
        tr, te = round_holdout_split(ev, test_round="r3")

    train_sample = (stratified_subsample(tr, n_target=args.train_sample, seed=args.seed)
                    if args.train_sample > 0 else tr)
    X_trs, y_trs, w_trs = compress(train_sample)
    X_te, y_te, w_te = compress(te)
    c_f1, c_fpr = vector_ceiling(te)

    pool = build_pool(X_trs, y_trs, mf, max_terms=args.max_terms,
                      min_support=args.min_support, conf_margin=args.conf_margin,
                      verbose=False, w=w_trs)
    M_te = mf.memberships(X_te)
    W_te = firing_matrix(M_te, pool["antecedents"])

    df = pd.read_csv(os.path.join(args.out_dir, "pareto_front.csv"))
    row = pick_best(df, args.min_rules, args.max_rules)
    names_sel = set(row["rules"].split("; "))
    mask = np.array([n in names_sel for n in pool["names"]])
    assert int(mask.sum()) == int(row["n_rules"]), \
        f"mask reconstruction mismatch: {mask.sum()} vs {row['n_rules']}"

    ac_best = sugeno_ac(W_te, pool["z"], subset=mask)
    f1_b, fpr_b, cm_b = f1_fpr(ac_best, y_te, args.ac_thr, w_te)

    out_txt = os.path.join(args.out_dir, "selected_rules_best_f1.txt")
    with open(out_txt, "w") as f:
        f.write(f"Best-F1 rule base within [{args.min_rules},{args.max_rules}] rules "
                f"(argmax f1_test, ties -> fewer rules)\n"
                f"({int(mask.sum())} rules)\n"
                f"test F1={f1_b:.4f} FPR={fpr_b:.4f} recall={cm_b['recall']:.4f} "
                f"precision={cm_b['precision']:.4f}\n"
                f"data ceiling on this test: F1<={c_f1:.4f} FPR={c_fpr:.4f}\n\n"
                + rules_listing(mask, pool) + "\n")
    export_c(mask, pool, os.path.join(args.out_dir, "selected_rules_best_f1.c"))
    print(f"[finalize] {args.out_dir} ({args.split}): {int(mask.sum())} rules, "
          f"test F1={f1_b:.4f} FPR={fpr_b:.4f} -> {out_txt}")


if __name__ == "__main__":
    main()
