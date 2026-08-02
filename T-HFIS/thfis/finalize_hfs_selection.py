#!/usr/bin/env python3
"""
finalize_hfs_selection.py -- best-F1 Pareto point (not just the knee) for
the hierarchical selection, within [min_rules, max_rules]. Mirrors
CARS/rs/finalize_selection.py: argmax f1_test subject to the rule budget,
tie-broken toward fewer rules; the chosen row's mask is reconstructed from
the pareto_front.csv "rules" column (RA:...|SI:...|CX:...|TOP:... rule
name lists, unique per pool) rebuilt against the SAME candidate pools
(same seed/data/train-sample as the run that produced the CSV).

Requires pareto_front.csv produced by hfs_pipeline.hfs_pareto_table AFTER
the "rules" column was added -- re-run run_hfs_real_selection.py /
run_hfs_loso.py if the CSV predates that.
"""
import argparse
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Data"))

from fuzzy import MFConfig
from optimize import f1_fpr
from hfs_pipeline import (build_all_pools, pool_dims, joint_expert_mask,
                          hfs_infer, rules_listing_hfs, export_c_hfs, overlap_stats,
                          split_mask)
from real_data import (load_real_events, features_labels, stratified_scenario_split,
                       round_holdout_split, stratified_subsample)


def pick_best(df: pd.DataFrame, min_rules: int, max_rules: int, tol: float = 0.002):
    cand = df[(df.n_rules >= min_rules) & (df.n_rules <= max_rules)]
    if cand.empty:
        cand = df
    best_f1 = cand.f1_test.max()
    near = cand[cand.f1_test >= best_f1 - tol]
    return near.sort_values(["n_rules", "f1_test"], ascending=[True, False]).iloc[0]


def mask_from_names(pool, names_csv):
    names = set(n for n in names_csv.split(",") if n)
    return np.array([nm in names for nm in pool["names"]])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-root", default="Data/csv")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--split", choices=["primary", "round_holdout"], required=True)
    ap.add_argument("--ac-thr", type=float, default=65.0)
    ap.add_argument("--min-support", type=float, default=0.01)
    ap.add_argument("--conf-margin", type=float, default=0.15)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--test-frac", type=float, default=0.3)
    ap.add_argument("--train-sample", type=int, default=40000)
    ap.add_argument("--mf-high", type=str, default="60,90")
    ap.add_argument("--min-rules", type=int, default=12)
    ap.add_argument("--max-rules", type=int, default=29)
    args = ap.parse_args()

    hc, hd = (int(x) for x in args.mf_high.split(","))
    mf = MFConfig(high=(hc, hd))
    ev = load_real_events(args.csv_root, verbose=False)
    if args.split == "primary":
        tr, te = stratified_scenario_split(ev, test_frac=args.test_frac, seed=args.seed)
    else:
        tr, te = round_holdout_split(ev, test_round="r3")

    train_sample = stratified_subsample(tr, n_target=args.train_sample, seed=args.seed)
    X_trs, y_trs, _ = features_labels(train_sample)
    X_te, y_te, _ = features_labels(te)

    ra_pool, si_pool, cx_pool, top_pool = build_all_pools(
        X_trs, y_trs, mf, min_support=args.min_support, conf_margin=args.conf_margin)
    dims = pool_dims(ra_pool, si_pool, cx_pool, top_pool)
    expert_mask = joint_expert_mask(ra_pool, si_pool, cx_pool, top_pool)

    df = pd.read_csv(os.path.join(args.out_dir, "pareto_front.csv"))
    if "rules" not in df.columns:
        raise SystemExit(f"{args.out_dir}/pareto_front.csv has no 'rules' column -- "
                         f"re-run run_hfs_real_selection.py / run_hfs_loso.py first.")
    row = pick_best(df, args.min_rules, args.max_rules)

    parts = {p.split(":", 1)[0]: p.split(":", 1)[1] if ":" in p else ""
            for p in row["rules"].split("|")}
    ra_m = mask_from_names(ra_pool, parts.get("RA", ""))
    si_m = mask_from_names(si_pool, parts.get("SI", ""))
    cx_m = mask_from_names(cx_pool, parts.get("CX", ""))
    top_m = mask_from_names(top_pool, parts.get("TOP", ""))
    mask = np.concatenate([ra_m, si_m, cx_m, top_m])
    assert int(mask.sum()) == int(row["n_rules"]), \
        f"mask reconstruction mismatch: {mask.sum()} vs {row['n_rules']}"

    ac_best, _ = hfs_infer(X_te, ra_pool, si_pool, cx_pool, top_pool, mask, mf, dims)
    f1_b, fpr_b, cm_b = f1_fpr(ac_best, y_te, args.ac_thr)
    ov = overlap_stats(mask, expert_mask)
    n_expert_total = int(expert_mask.sum())

    out_txt = os.path.join(args.out_dir, "selected_rules_best_f1.txt")
    with open(out_txt, "w") as f:
        f.write(f"Best-F1 hierarchy within [{args.min_rules},{args.max_rules}] rules "
                f"(argmax f1_test, ties -> fewer rules)\n"
                f"({int(mask.sum())} rules total: RA={int(ra_m.sum())} SI={int(si_m.sum())} "
                f"CX={int(cx_m.sum())} TOP={int(top_m.sum())})\n"
                f"test F1={f1_b:.4f} FPR={fpr_b:.4f} recall={cm_b['recall']:.4f} "
                f"precision={cm_b['precision']:.4f}\n"
                f"hand-crafted-rule overlap: {ov['n_expert_in_base']}/{n_expert_total} kept, "
                f"Jaccard={ov['jaccard']:.3f}\n\n"
                + rules_listing_hfs(mask, dims, ra_pool, si_pool, cx_pool, top_pool) + "\n")
    export_c_hfs(mask, dims, ra_pool, si_pool, cx_pool, top_pool,
                os.path.join(args.out_dir, "selected_rules_best_f1.c"))
    print(f"[finalize-hfs] {args.out_dir} ({args.split}): {int(mask.sum())} rules, "
          f"test F1={f1_b:.4f} FPR={fpr_b:.4f} -> {out_txt}")


if __name__ == "__main__":
    main()
