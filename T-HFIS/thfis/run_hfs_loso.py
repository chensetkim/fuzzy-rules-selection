#!/usr/bin/env python3
"""
run_hfs_loso.py -- Leave-one-scenario-out validation for the hierarchical
(T-HFIS) pipeline. See CARS/rs/run_loso.py for the rationale (this is the
same check, applied to the joint RA/SI/CX/TOP selection).
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "..", "Data"))

from fuzzy import MFConfig
from real_data import load_real_events, scenario_holdout_split
from run_hfs_real_selection import run_one


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv-root", default="Data/csv")
    ap.add_argument("--out-root", default="T-HFIS/rule_selection_real/loso")
    ap.add_argument("--ac-thr", type=float, default=65.0)
    ap.add_argument("--max-rules", type=int, default=29)
    ap.add_argument("--min-rules", type=int, default=12)
    ap.add_argument("--min-support", type=float, default=0.01)
    ap.add_argument("--conf-margin", type=float, default=0.15)
    ap.add_argument("--pop", type=int, default=80)
    ap.add_argument("--gens", type=int, default=100)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--train-sample", type=int, default=30000)
    ap.add_argument("--mf-high", type=str, default="60,90")
    args = ap.parse_args()

    hc, hd = (int(x) for x in args.mf_high.split(","))
    mf = MFConfig(high=(hc, hd))
    ev = load_real_events(args.csv_root)

    results = []
    for scen in ["S1", "S2", "S3", "S4", "S5", "S6"]:
        trh, teh = scenario_holdout_split(ev, test_scenario=scen)
        r = run_one(f"hfs-loso-{scen}", trh, teh, os.path.join(args.out_root, scen),
                   mf, args,
                   note=f"Leave-one-scenario-out: trained on all scenarios except "
                        f"{scen}; evaluated on {scen} only (unseen attack type).")
        results.append(r)

    print("\n=== SUMMARY (T-HFIS, leave-one-scenario-out) ===")
    for r in results:
        print(f"{r['tag']:14} {r['n_rules']:2d} rules | F1={r['f1']:.4f} "
              f"FPR={r['fpr']:.4f}  (hand-crafted F1={r['ref_f1']:.4f})")
    import numpy as np
    f1s = np.array([r["f1"] for r in results])
    print(f"\nmean F1={f1s.mean():.4f}  std={f1s.std():.4f}  min={f1s.min():.4f}  max={f1s.max():.4f}")


if __name__ == "__main__":
    main()
