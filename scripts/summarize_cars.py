#!/usr/bin/env python3
"""
summarize_cars.py -- Build SUMMARY.md for one run_cars.sh run directory
=====================================================================
Reads, for every seed folder of a run:
    <seed>/primary/selected_rules.txt            knee base
    <seed>/primary/selected_rules_best_f1.txt    best-F1 re-pick
    <seed>/round_holdout/...                     same
    <seed>/loso/S1..S6/selected_rules.txt        knee base per held-out scenario
and the R1-R18 baseline lines printed in <seed>/logs/*.log.

Usage:
    python3 scripts/summarize_cars.py outputs/cars/run_<stamp>
"""
from __future__ import annotations
import glob
import os
import re
import sys

import numpy as np

METRIC_RE = re.compile(r"test F1=([\d.]+) FPR=([\d.]+) recall=([\d.]+) precision=([\d.]+)")
NRULES_RE = re.compile(r"\((\d+) rules\)")
KEPT_RE = re.compile(r"expert overlap: (\d+)/18")
BASE_RE = re.compile(r"^\[([\w-]+)\] expert R1-R18 on this test: F1=([\d.]+) FPR=([\d.]+) "
                     r"recall=([\d.]+) precision=([\d.]+)", re.M)


def read_base(path: str):
    """-> dict(n, f1, fpr, rec, prec, kept) from a selected_rules*.txt, or None."""
    if not os.path.isfile(path):
        return None
    txt = open(path).read()
    m, n, k = METRIC_RE.search(txt), NRULES_RE.search(txt), KEPT_RE.search(txt)
    if not (m and n):
        return None
    f1, fpr, rec, prec = (float(x) for x in m.groups())
    return dict(n=int(n.group(1)), f1=f1, fpr=fpr, rec=rec, prec=prec,
                kept=int(k.group(1)) if k else None)


def read_baselines(seed_dir: str):
    """-> {tag: dict(f1, fpr, rec, prec)} for the R1-R18 base, from the step logs."""
    out = {}
    for log in glob.glob(os.path.join(seed_dir, "logs", "*.log")):
        for tag, f1, fpr, rec, prec in BASE_RE.findall(open(log, errors="replace").read()):
            out[tag] = dict(f1=float(f1), fpr=float(fpr), rec=float(rec), prec=float(prec))
    return out


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
    run_dir = sys.argv[1].rstrip("/")
    seed_dirs = sorted(d for d in glob.glob(os.path.join(run_dir, "seed_*")) if os.path.isdir(d))
    if not seed_dirs:
        sys.exit(f"no seed_* folders under {run_dir}")
    seeds = [os.path.basename(d).removeprefix("seed_") for d in seed_dirs]

    # (row label, path inside a seed dir, baseline tag in the logs)
    rows = [("primary — knee", "primary/selected_rules.txt", "primary"),
            ("primary — best-F1", "primary/selected_rules_best_f1.txt", "primary"),
            ("round-holdout — knee", "round_holdout/selected_rules.txt", "round-holdout"),
            ("round-holdout — best-F1", "round_holdout/selected_rules_best_f1.txt", "round-holdout")]
    rows += [(f"LOSO {s} — knee", f"loso/{s}/selected_rules.txt", f"loso-{s}")
             for s in ["S1", "S2", "S3", "S4", "S5", "S6"]]

    bases = {d: read_baselines(d) for d in seed_dirs}
    lines = [f"# CARS run summary — `{os.path.basename(run_dir)}`", "",
             f"Seeds: {', '.join(seeds)}" + (" (values are mean ± std over seeds)" if len(seeds) > 1 else ""),
             "", "Settings: see `config.txt`.", "",
             "| Split | Rules | F1 | FPR | Recall | Precision | Expert rules kept | R1–R18 F1 | R1–R18 FPR |",
             "|---|---|---|---|---|---|---|---|---|"]
    loso_f1 = {d: [] for d in seed_dirs}
    for label, rel, tag in rows:
        res = [read_base(os.path.join(d, rel)) for d in seed_dirs]
        if all(r is None for r in res):
            continue
        get = lambda k: [r[k] if r else None for r in res]
        bl = [bases[d].get(tag) for d in seed_dirs]
        bget = lambda k: [b[k] if b else None for b in bl]
        lines.append(f"| {label} | {fmt(get('n'), 1) if len(seeds) > 1 else fmt(get('n'))} | "
                     f"{fmt(get('f1'))} | {fmt(get('fpr'))} | {fmt(get('rec'))} | {fmt(get('prec'))} | "
                     f"{fmt(get('kept'), 1) if len(seeds) > 1 else fmt(get('kept'))}/18 | "
                     f"{fmt(bget('f1'))} | {fmt(bget('fpr'))} |")
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
