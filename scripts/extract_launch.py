#!/usr/bin/env python3
"""
extract_launch.py -- per-attacker attack-launch times from the Cooja logs
=========================================================================
Every attacker mote prints one "[ATK-LAUNCHED]" line when its attack starts.
This writes one row per attacker and run:

    run,mote_id,launch_ms
    3-1-21-9-150-S5-exp5438-mobile-2,29,201080

`run` is the log/CSV file name without extension, so a row joins to its CSV in
data/processed/. common/real_data.py labels an attacker's events as attack from
launch_ms on (LABEL_START=launch), instead of a fixed start time.

Usage:
    python3 scripts/extract_launch.py [data/raw] [data/attack_launch.csv] [--time-unit us|ms]
"""
import argparse
import csv
import glob
import os
import re
import sys

LAUNCH = re.compile(r"^\s*(\d+)\s+(?:ID:)?(\d+)\s+.*\[ATK-LAUNCHED\]")
BOOT = re.compile(r"^\s*(\d+)\s+(?:ID:)?(\d+)\s+.*Starting 2H-FuzzRID attacker")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log_dir", nargs="?", default="data/raw")
    ap.add_argument("out_csv", nargs="?", default="data/attack_launch.csv")
    ap.add_argument("--time-unit", choices=["us", "ms"], default="us")
    args = ap.parse_args()

    logs = sorted(glob.glob(os.path.join(args.log_dir, "*.log")))
    if not logs:
        sys.exit(f"no .log files in {args.log_dir}")
    rows, problems = [], []
    for fn in logs:
        run = os.path.splitext(os.path.basename(fn))[0]
        launch, booted = {}, set()
        for ln in open(fn, errors="replace"):
            m = LAUNCH.match(ln)
            if m:
                stamp, mote = int(m.group(1)), int(m.group(2))
                ms = stamp // 1000 if args.time_unit == "us" else stamp
                if mote in launch:
                    problems.append(f"{run}: mote {mote} launched twice")
                launch.setdefault(mote, ms)
            b = BOOT.match(ln)
            if b:
                booted.add(int(b.group(2)))
        for mote in sorted(booted - set(launch)):
            problems.append(f"{run}: attacker {mote} has no [ATK-LAUNCHED] line")
        rows += [(run, mote, ms) for mote, ms in sorted(launch.items())]

    os.makedirs(os.path.dirname(os.path.abspath(args.out_csv)), exist_ok=True)
    with open(args.out_csv, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["run", "mote_id", "launch_ms"])
        w.writerows(rows)
    ms = [r[2] for r in rows]
    print(f"[launch] {len(logs)} logs -> {len(rows)} attacker launches -> {args.out_csv}")
    print(f"[launch] launch time {min(ms) / 1000:.1f}..{max(ms) / 1000:.1f} s")
    if problems:
        print("[launch] problems:\n  " + "\n  ".join(problems), file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
