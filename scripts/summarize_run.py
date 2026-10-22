#!/usr/bin/env python3
"""
summarize_run.py -- Build SUMMARY.md for one run_cars.sh / run_thfis.sh run
=========================================================================
Reads, for every seed folder of a run:
    <seed>/primary/selected_rules.txt            knee base
    <seed>/primary/selected_rules_best_f1.txt    best-F1 re-pick
    <seed>/round_holdout/...                     same
    <seed>/loso/S1..S6/selected_rules.txt        knee base per held-out scenario

Usage:
    python3 scripts/summarize_run.py cars  outputs/cars/run_<stamp>
    python3 scripts/summarize_run.py thfis outputs/thfis/run_<stamp>
"""
from __future__ import annotations
import glob
import os
import re
import sys

import numpy as np

METRIC_RE = re.compile(r"test F1=([\d.]+) FPR=([\d.]+) recall=([\d.]+) precision=([\d.]+)")
NRULES_RE = re.compile(r"\((\d+) rules")          # "(18 rules)" / "(12 rules total..."

TITLES = {"cars": "CARS", "thfis": "T-HFIS"}


def read_base(path: str):
    """-> dict(n, f1, fpr, rec, prec) from a selected_rules*.txt, or None."""
    if not os.path.isfile(path):
        return None
    txt = open(path).read()
    m, n = METRIC_RE.search(txt), NRULES_RE.search(txt)
    if not (m and n):
        return None
    f1, fpr, rec, prec = (float(x) for x in m.groups())
    return dict(n=int(n.group(1)), f1=f1, fpr=fpr, rec=rec, prec=prec)


def fmt(vals, digits=4):
    """Single value, or mean ± std over seeds."""
    vals = [v for v in vals if v is not None]
    if not vals:
        return "–"
    if len(vals) == 1:
        return f"{vals[0]:.{digits}f}" if isinstance(vals[0], float) else str(vals[0])
    a = np.asarray(vals, dtype=float)
    return f"{a.mean():.{digits}f} ± {a.std():.{digits}f}"


def main():
    if len(sys.argv) != 3 or sys.argv[1] not in TITLES:
        sys.exit(__doc__)
    title = TITLES[sys.argv[1]]
    run_dir = sys.argv[2].rstrip("/")
    seed_dirs = sorted(d for d in glob.glob(os.path.join(run_dir, "seed_*")) if os.path.isdir(d))
    if not seed_dirs:
        sys.exit(f"no seed_* folders under {run_dir}")
    seeds = [os.path.basename(d).removeprefix("seed_") for d in seed_dirs]
    multi = len(seeds) > 1

    rows = [("primary — knee", "primary/selected_rules.txt"),
            ("primary — best-F1", "primary/selected_rules_best_f1.txt"),
            ("round-holdout — knee", "round_holdout/selected_rules.txt"),
            ("round-holdout — best-F1", "round_holdout/selected_rules_best_f1.txt")]
    rows += [(f"LOSO {s} — knee", f"loso/{s}/selected_rules.txt")
             for s in ["S1", "S2", "S3", "S4", "S5", "S6"]]

    lines = [f"# {title} run summary — `{os.path.basename(run_dir)}`", "",
             f"Seeds: {', '.join(seeds)}" + (" (values are mean ± std over seeds)" if multi else ""),
             "", "Settings: see `config.txt`.", "",
             "| Split | Rules | F1 | FPR | Recall | Precision |",
             "|---|---|---|---|---|---|"]
    loso_f1 = {d: [] for d in seed_dirs}
    for label, rel in rows:
        res = [read_base(os.path.join(d, rel)) for d in seed_dirs]
        if all(r is None for r in res):
            continue
        get = lambda k: [r[k] if r else None for r in res]
        lines.append(f"| {label} | {fmt(get('n'), 1) if multi else fmt(get('n'))} | "
                     f"{fmt(get('f1'))} | {fmt(get('fpr'))} | {fmt(get('rec'))} | {fmt(get('prec'))} |")
        if label.startswith("LOSO"):
            for d, r in zip(seed_dirs, res):
                if r:
                    loso_f1[d].append(r["f1"])

    means = [np.mean(v) for v in loso_f1.values() if len(v) == 6]
    if means:
        lines += ["", f"LOSO mean F1 over S1–S6: **{fmt(means)}**"]
    lines += ["", "Deployable rule bases: `seed_<s>/primary/selected_rules.c` (knee) and "
              "`selected_rules_best_f1.c` (best-F1). The firmware membership functions must "
              "match `MF_HIGH` in `config.txt`.", ""]

    out = os.path.join(run_dir, "SUMMARY.md")
    open(out, "w").write("\n".join(lines))
    print("\n".join(lines))
    print(f"-> {out}")


if __name__ == "__main__":
    main()
