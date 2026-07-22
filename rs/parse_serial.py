#!/usr/bin/env python3
"""
parse_serial.py -- Cooja serial log -> rule-selection event CSV
===============================================================
Converts one captured Cooja simulation log into one schema-conformant
events CSV for run_selection.py.

Expected input: the output of the Cooja simulation script

    TIMEOUT(1800000);
    while (true) { log.log(time + " " + id + " " + msg + "\\n"); YIELD(); }

i.e. one line per serial write, "<time> <mote_id> <serial text>", where the
serial text carries the firmware's per-detection marker line (see EVT below).

Usage:
    python3 parse_serial.py sim.log ../sample_csv/S1_decrease_jump_run1.csv \\
        [--time-unit us|ms] [--atk-nodes 5,6,7,8,9,10]

The output schema is fixed by data.py:
    sim_ms,mote_id,src,R,Rhat,e,v1..v7,AC,ML,t,type,action
Of these, data.py reads only type, mote_id, src, t and v1..v7; the rest are
carried for traceability (AC is the firmware's own inference output, which is
what lets you cross-check fuzzy.py against the deployed implementation).

See fuzzy_rules_selection.md section 12 for the full contract.
"""
import argparse
import csv
import re
import sys
from pathlib import Path

COLS = ["sim_ms", "mote_id", "src", "R", "Rhat", "e",
        "v1", "v2", "v3", "v4", "v5", "v6", "v7", "AC", "ML",
        "t", "type", "action"]

# Cooja script line: "<time> <mote_id> <serial text>"
LOG = re.compile(r"^\s*(\d+)\s+(\d+)\s+(.*)$")

# Firmware payload.  <<< ALIGN THIS WITH YOUR printf >>>
#   printf("FUZZRID,DET,%u,%d,%d,%d,%u,%u,%u,%u,%u,%u,%u,%u,%u\n",
#          src_id, R, Rhat, e, v1..v7, ac, ml);
EVT = re.compile(
    r"FUZZRID,DET,"
    r"(?P<src>\d+),(?P<R>-?\d+),(?P<Rhat>-?\d+),(?P<e>-?\d+),"
    r"(?P<v1>\d+),(?P<v2>\d+),(?P<v3>\d+),(?P<v4>\d+),"
    r"(?P<v5>\d+),(?P<v6>\d+),(?P<v7>\d+),"
    r"(?P<AC>\d+),(?P<ML>\d+)\s*$")

V = [f"v{i}" for i in range(1, 8)]


def parse(log_path, time_unit="us", dedup=True):
    """Return a list of schema-conformant row dicts parsed from log_path.

    dedup drops only rows identical in EVERY field, which is the signature of a
    replayed capture or a mote reboot. It deliberately does NOT key on
    (sim_ms, mote_id, src): one observer legitimately emits several detection
    events for the same source within one millisecond, with different evidence
    vectors, and keying on that triple silently discards real observations.
    """
    rows, seen, malformed, dropped = [], set(), 0, 0
    for ln in Path(log_path).read_text(errors="replace").splitlines():
        m = LOG.match(ln)
        if not m:
            continue
        stamp, mote_id, payload = m.groups()
        e = EVT.search(payload)
        if not e:
            if "FUZZRID" in payload:       # marker present but shape wrong
                malformed += 1             # -> truncated line or format drift
            continue
        d = e.groupdict()
        sim_ms = int(stamp) // 1000 if time_unit == "us" else int(stamp)

        for k in V:                        # fail loudly on scale errors
            if not 0 <= int(d[k]) <= 100:
                raise ValueError(f"{k}={d[k]} outside 0..100 -- features must be "
                                 f"normalised before printing (line: {ln[:80]})")

        row = {"sim_ms": sim_ms, "mote_id": int(mote_id),
               "src": int(d["src"]), "R": int(d["R"]),
               "Rhat": int(d["Rhat"]), "e": int(d["e"]),
               **{k: int(d[k]) for k in V},
               "AC": int(d["AC"]), "ML": int(d["ML"]),
               "t": sim_ms // 1000,        # SECONDS -- data.py compares against it
               "type": "detection", "action": ""}

        if dedup:
            key = tuple(row[c] for c in COLS)
            if key in seen:
                dropped += 1
                continue
            seen.add(key)

        rows.append(row)

    if malformed:
        print(f"[warn] {malformed} lines carried the marker but did not match EVT "
              f"-- check for serial truncation or a printf change", file=sys.stderr)
    if dropped:
        print(f"[warn] dropped {dropped} fully-identical duplicate rows "
              f"(replayed capture or mote reboot?)", file=sys.stderr)
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("log")
    ap.add_argument("out_csv")
    ap.add_argument("--time-unit", choices=["us", "ms"], default="us",
                    help="unit of the Cooja script's `time` variable (verify once "
                         "for your Cooja version)")
    ap.add_argument("--atk-nodes", default=None,
                    help="comma-separated attacker IDs, for the summary only")
    ap.add_argument("--no-dedup", action="store_true",
                    help="keep fully-identical duplicate rows")
    args = ap.parse_args()

    rows = parse(args.log, args.time_unit, dedup=not args.no_dedup)
    if not rows:
        sys.exit("no detection events parsed -- check LOG/EVT against your log")

    out = Path(args.out_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open("w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        w.writeheader()
        w.writerows(rows)

    ts = [r["t"] for r in rows]
    print(f"[parse] {len(rows)} events -> {out}")
    print(f"[parse] t range {min(ts)}..{max(ts)} s | "
          f"observers={len({r['mote_id'] for r in rows})} "
          f"sources={len({r['src'] for r in rows})}")
    if args.atk_nodes:
        atk = {int(x) for x in args.atk_nodes.split(",")}
        n = sum(r["src"] in atk for r in rows)
        print(f"[parse] rows with src in attacker set: {n} ({n/len(rows):.1%})")
        if n == 0:
            print("[parse] WARNING: no attacker-sourced rows -- wrong --atk-nodes, "
                  "or src/mote_id are swapped in EVT", file=sys.stderr)


if __name__ == "__main__":
    main()
