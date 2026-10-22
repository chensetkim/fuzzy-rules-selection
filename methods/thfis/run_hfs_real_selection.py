#!/usr/bin/env python3
"""
run_hfs_real_selection.py -- Joint hierarchical (T-HFIS) rule selection on
the real data/processed corpus.

Mirrors methods/cars/run_real_selection.py: same PRIMARY (scenario-stratified)
+ ROUND-HOLDOUT (mobile r1+r2 -> unseen mobile r3) design, same
train-sample-for-search / full-set-for-reporting split, but selects rules
jointly across the four T-HFIS sub-FIS units (RA/SI/CX/TOP) instead of one
flat 7-input engine. See hfs_pipeline.py for the methodology.
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "common"))

from fuzzy import set_arithmetic, MFConfig
from optimize import knee_solution, f1_fpr
from hfs_pipeline import (build_all_pools, pool_dims,
                          run_nsga2_hfs, hfs_pareto_table, rules_listing_hfs,
                          export_c_hfs, hfs_infer)
from real_data import (load_real_events, features_labels, stratified_scenario_split,
                       round_holdout_split, stratified_subsample)


def run_one(tag, ev_train, ev_test, out_dir, mf, args, note=""):
    os.makedirs(out_dir, exist_ok=True)
    train_sample = stratified_subsample(ev_train, n_target=args.train_sample, seed=args.seed)
    print(f"\n=== [hfs:{tag}] train={len(ev_train)} (sampled {len(train_sample)} for "
          f"pool/NSGA-II) test={len(ev_test)} ===")
    X_trs, y_trs, _ = features_labels(train_sample)
    X_te, y_te, _ = features_labels(ev_test)

    ra_pool, si_pool, cx_pool, top_pool = build_all_pools(
        X_trs, y_trs, mf, min_support=args.min_support, conf_margin=args.conf_margin)
    dims = pool_dims(ra_pool, si_pool, cx_pool, top_pool)
    print(f"[hfs:{tag}] pool sizes: RA={dims[0]} SI={dims[1]} CX={dims[2]} TOP={dims[3]} "
          f"(total {sum(dims)} candidate bits)")

    masks, F, dims = run_nsga2_hfs(ra_pool, si_pool, cx_pool, top_pool, y_trs, mf,
                                   ac_thr=args.ac_thr, max_rules=args.max_rules,
                                   min_rules=args.min_rules, pop_size=args.pop,
                                   n_gen=args.gens, seed=args.seed)
    print(f"[hfs:{tag}] Pareto front: {len(masks)} non-dominated hierarchies")

    tab = hfs_pareto_table(masks, F, dims, ra_pool, si_pool, cx_pool, top_pool, mf,
                           X_te, y_te, args.ac_thr)
    tab.to_csv(os.path.join(out_dir, "pareto_front.csv"), index=False)

    k = knee_solution(F)
    best = masks[k]
    ac_best, _ = hfs_infer(X_te, ra_pool, si_pool, cx_pool, top_pool, best, mf, dims)
    f1_b, fpr_b, cm_b = f1_fpr(ac_best, y_te, args.ac_thr)
    with open(os.path.join(out_dir, "selected_rules.txt"), "w") as f:
        f.write(f"{note}\nKnee-point hierarchy ({int(best.sum())} rules total)\n"
                f"test F1={f1_b:.4f} FPR={fpr_b:.4f} recall={cm_b['recall']:.4f} "
                f"precision={cm_b['precision']:.4f}\n\n"
                + rules_listing_hfs(best, dims, ra_pool, si_pool, cx_pool, top_pool) + "\n")
    export_c_hfs(best, dims, ra_pool, si_pool, cx_pool, top_pool,
                os.path.join(out_dir, "selected_rules.c"), mf)

    print(f"[hfs:{tag}] knee base: {int(best.sum())} rules | test F1={f1_b:.4f} "
          f"FPR={fpr_b:.4f}")
    return dict(tag=tag, f1=f1_b, fpr=fpr_b, cm=cm_b, n_rules=int(best.sum()))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-root", default="data/processed")
    ap.add_argument("--out-root", default="outputs/thfis")
    ap.add_argument("--ac-thr", type=float, default=65.0)
    ap.add_argument("--max-rules", type=int, default=35)
    ap.add_argument("--min-rules", type=int, default=12)
    ap.add_argument("--min-support", type=float, default=0.01)
    ap.add_argument("--conf-margin", type=float, default=0.15)
    ap.add_argument("--pop", type=int, default=150)
    ap.add_argument("--gens", type=int, default=250)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--test-frac", type=float, default=0.3)
    ap.add_argument("--train-sample", type=int, default=40000)
    ap.add_argument("--mf-high", type=str, default="50,80")
    ap.add_argument("--arith", choices=["int", "float"], default="int",
                    help="int = firmware integer arithmetic (default), float = continuous model")
    args = ap.parse_args()
    set_arithmetic(args.arith)

    hc, hd = (int(x) for x in args.mf_high.split(","))
    mf = MFConfig(high=(hc, hd))

    ev = load_real_events(args.csv_root)

    tr, te = stratified_scenario_split(ev, test_frac=args.test_frac, seed=args.seed)
    primary = run_one("primary", tr, te, os.path.join(args.out_root, "primary"), mf, args,
                      note="Scenario-stratified 70/30 split (all env/round/atkcount "
                           "pooled; all 6 attack variants on both sides).")

    trh, teh = round_holdout_split(ev, test_round="r3")
    holdout = run_one("round-holdout", trh, teh,
                      os.path.join(args.out_root, "round_holdout"), mf, args,
                      note="Independent re-selection trained on mobile r1+r2 + "
                           "static r1 only; evaluated on mobile r3, a simulation "
                           "repetition never used for candidate generation or "
                           "NSGA-II fitness. Tests generalisation, not deployed.")

    print("\n=== SUMMARY (hierarchical T-HFIS) ===")
    print(f"primary:       {primary['n_rules']:2d} rules | test F1={primary['f1']:.4f} "
          f"FPR={primary['fpr']:.4f}")
    print(f"round-holdout: {holdout['n_rules']:2d} rules | unseen-round F1={holdout['f1']:.4f} "
          f"FPR={holdout['fpr']:.4f}")
    gap = primary['f1'] - holdout['f1']
    print(f"F1 gap (primary test vs unseen-round holdout): {gap:+.4f} "
          f"{'(small -> low overfit risk)' if abs(gap) < 0.05 else '(check for overfitting)'}")


if __name__ == "__main__":
    main()
