#!/usr/bin/env python3
"""
run_selection.py -- Offline fuzzy rule selection for 2H-FuzzRID
===============================================================
Wang-Mendel + bounded-enumeration candidate generation, NSGA-II
multi-objective subset selection, evaluated against the deployed
expert base R1-R18.

Usage:
    python3 run_selection.py <events_csv_dir> <output_dir> \
        [--atk-id-start 33] [--atk-start-s 300] [--atk-nodes 5,6,7] \
        [--ac-thr 65] [--max-terms 4] [--max-rules 30] \
        [--pop 120] [--gens 200] [--seed 42] [--test-frac 0.3] \
        [--mf-high 60,90]

<events_csv_dir> is the directory of parse_serial.py outputs
(e.g. results/raw/csv/ with S1_run1.csv ... S6_runN.csv).
"""

import argparse
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fuzzy import MFConfig, firing_matrix, expert_arrays
from data import load_events_dir, features_labels, train_test_split_by_scenario
from candidates import build_pool
from optimize import run_nsga2, knee_solution, f1_fpr
from fuzzy import sugeno_ac
from report import pareto_table, rules_listing, export_c, overlap_stats


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_dir")
    ap.add_argument("out_dir")
    ap.add_argument("--atk-id-start", type=int, default=33)
    ap.add_argument("--atk-start-s", type=int, default=300)
    ap.add_argument("--atk-nodes", type=str, default=None,
                    help="comma-separated attacker mote IDs (overrides --atk-id-start)")
    ap.add_argument("--ac-thr", type=float, default=65.0)
    ap.add_argument("--max-terms", type=int, default=4)
    ap.add_argument("--max-rules", type=int, default=30)
    ap.add_argument("--min-support", type=float, default=0.005)
    ap.add_argument("--conf-margin", type=float, default=0.15)
    ap.add_argument("--pop", type=int, default=120)
    ap.add_argument("--gens", type=int, default=200)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--test-frac", type=float, default=0.3)
    ap.add_argument("--mf-high", type=str, default="60,90",
                    help="High-set breakpoints c,d (use 50,80 for pre-Mar-2026 base)")
    args = ap.parse_args()

    os.makedirs(args.out_dir, exist_ok=True)
    atk_nodes = ({int(x) for x in args.atk_nodes.split(",")}
                 if args.atk_nodes else None)
    hc, hd = (int(x) for x in args.mf_high.split(","))
    mf = MFConfig(high=(hc, hd))

    # ---- 1. Load & label -------------------------------------------------
    ev = load_events_dir(args.csv_dir, atk_nodes=atk_nodes,
                         atk_id_start=args.atk_id_start,
                         atk_start_s=args.atk_start_s)
    print(f"[data] {len(ev)} detection events | attack={int(ev['y'].sum())} "
          f"benign={int((1 - ev['y']).sum())} | scenarios="
          f"{sorted(ev['scenario'].unique())}")
    tr, te = train_test_split_by_scenario(ev, test_frac=args.test_frac,
                                          seed=args.seed)
    X_tr, y_tr, _ = features_labels(tr)
    X_te, y_te, _ = features_labels(te)

    # ---- 2. Candidate pool (train only) ---------------------------------
    pool = build_pool(X_tr, y_tr, mf, max_terms=args.max_terms,
                      min_support=args.min_support,
                      conf_margin=args.conf_margin)

    # ---- 3. Expert baseline on the same split ---------------------------
    e_ants, e_z, _ = expert_arrays()
    M_te = mf.memberships(X_te)
    W_te = firing_matrix(M_te, pool["antecedents"])
    exp_mask = pool["expert_mask"]
    ac_exp = sugeno_ac(W_te, pool["z"], subset=exp_mask)
    f1_e, fpr_e, cm_e = f1_fpr(ac_exp, y_te, args.ac_thr)
    print(f"[expert R1-R18] test F1={f1_e:.4f} FPR={fpr_e:.4f} "
          f"recall={cm_e['recall']:.4f} precision={cm_e['precision']:.4f}")

    # ---- 4. NSGA-II ------------------------------------------------------
    masks, F = run_nsga2(pool, y_tr, ac_thr=args.ac_thr,
                         max_rules=args.max_rules, pop_size=args.pop,
                         n_gen=args.gens, seed=args.seed)
    print(f"[nsga2] Pareto front: {len(masks)} non-dominated rule bases")

    # ---- 5. Report -------------------------------------------------------
    tab = pareto_table(masks, F, pool, y_tr, W_te, y_te, args.ac_thr,
                       pool["names"])
    tab.to_csv(os.path.join(args.out_dir, "pareto_front.csv"), index=False)

    k = knee_solution(F)
    best = masks[k]
    ov = overlap_stats(best, exp_mask)
    f1_b, fpr_b, cm_b = f1_fpr(sugeno_ac(W_te, pool["z"], subset=best),
                               y_te, args.ac_thr)
    with open(os.path.join(args.out_dir, "selected_rules.txt"), "w") as f:
        f.write(f"Knee-point rule base ({int(best.sum())} rules)\n"
                f"test F1={f1_b:.4f} FPR={fpr_b:.4f} "
                f"recall={cm_b['recall']:.4f} precision={cm_b['precision']:.4f}\n"
                f"expert overlap: {ov['n_expert_in_base']}/18 expert rules kept, "
                f"Jaccard={ov['jaccard']:.3f}\n\n"
                + rules_listing(best, pool) + "\n")
    export_c(best, pool, os.path.join(args.out_dir, "selected_rules.c"))

    with open(os.path.join(args.out_dir, "overlap_report.txt"), "w") as f:
        f.write("base_id,n_rules,expert_in_base,jaccard,expert_coverage\n")
        for i, m in enumerate(masks):
            o = overlap_stats(m, exp_mask)
            f.write(f"{i},{o['n_selected']},{o['n_expert_in_base']},"
                    f"{o['jaccard']:.3f},{o['expert_coverage']:.3f}\n")

    print(f"[done] knee base: {int(best.sum())} rules | test F1={f1_b:.4f} "
          f"FPR={fpr_b:.4f} | expert rules kept={ov['n_expert_in_base']}/18")
    print(f"[done] outputs in {args.out_dir}: pareto_front.csv, "
          f"selected_rules.txt, selected_rules.c, overlap_report.txt")


if __name__ == "__main__":
    main()
