#!/usr/bin/env python3
"""
run_hfs_eval.py -- Flat R1-R18 vs T-HFIS head-to-head
=====================================================
Usage:
    python3 run_hfs_eval.py <events_csv_dir> [--atk-nodes 5,6,7,8,9,10]
        [--atk-start-s 300] [--ac-thr 65] [--mf-high 60,90]

Prints per-scenario and overall F1 / FPR / recall / precision for both
engines, the intermediate-variable summary, and the complexity table.
"""
import argparse
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fuzzy import MFConfig, firing_matrix, expert_arrays, sugeno_ac
from data import load_events_dir, features_labels
from optimize import f1_fpr
from hierarchy import THFIS


def flat_ac(X, mf):
    ants, z, _ = expert_arrays()
    M = mf.memberships(X)
    W = firing_matrix(M, ants)
    return sugeno_ac(W, z)


def metrics_line(tag, ac, y, thr):
    f1, fpr, cm = f1_fpr(ac, y, thr)
    return (f"{tag:28} F1={f1:.4f}  FPR={fpr:.4f}  "
            f"recall={cm['recall']:.4f}  precision={cm['precision']:.4f}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv_dir")
    ap.add_argument("--atk-nodes", type=str, default=None)
    ap.add_argument("--atk-id-start", type=int, default=33)
    ap.add_argument("--atk-start-s", type=int, default=300)
    ap.add_argument("--ac-thr", type=float, default=65.0)
    ap.add_argument("--mf-high", type=str, default="60,90")
    args = ap.parse_args()

    atk = ({int(x) for x in args.atk_nodes.split(",")} if args.atk_nodes else None)
    hc, hd = (int(x) for x in args.mf_high.split(","))
    mf = MFConfig(high=(hc, hd))

    ev = load_events_dir(args.csv_dir, atk_nodes=atk,
                         atk_id_start=args.atk_id_start,
                         atk_start_s=args.atk_start_s)
    X, y, groups = features_labels(ev)
    print(f"[data] {len(ev)} events | attack={int(y.sum())} "
          f"benign={int((1 - y).sum())}\n")

    hfs = THFIS(mf)
    ac_f = flat_ac(X, mf)
    ac_h = hfs.infer(X)
    ra, si, cx = hfs.intermediates(X)

    print("== Overall ==")
    print(metrics_line("flat Sugeno (R1-R18)", ac_f, y, args.ac_thr))
    print(metrics_line("T-HFIS (25 rules)", ac_h, y, args.ac_thr))

    print("\n== Per scenario ==")
    for s in sorted(set(groups)):
        m = groups == s
        print(f"[{s}] " + metrics_line("flat", ac_f[m], y[m], args.ac_thr))
        print(f"[{s}] " + metrics_line("T-HFIS", ac_h[m], y[m], args.ac_thr))

    print("\n== Intermediate variables (mean attack vs benign) ==")
    for name, v in (("RA", ra), ("SI", si), ("CX", cx)):
        print(f"{name}: attack={v[y == 1].mean():6.1f}   "
              f"benign={v[y == 0].mean():6.1f}")

    rows, grid, used = THFIS.complexity_table()
    print("\n== Complexity ==")
    print(f"{'unit':16}{'inputs':>7}{'full grid':>10}{'rules used':>12}")
    for name, n_in, g, u in rows:
        print(f"{name:16}{n_in:>7}{g:>10}{u:>12}")
    print(f"{'TOTAL':16}{'':>7}{grid:>10}{used:>12}")
    print(f"{'flat engine':16}{7:>7}{2187:>10}{18:>12}")
    print(f"\nGrid-space reduction: 2187 -> {grid}  ({2187/grid:.1f}x)")

    disagree = np.mean((ac_f >= args.ac_thr) != (ac_h >= args.ac_thr))
    print(f"\nDecision disagreement flat vs T-HFIS: {disagree*100:.2f}% of events")


if __name__ == "__main__":
    main()
