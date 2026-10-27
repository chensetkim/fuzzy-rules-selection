"""
real_data.py -- Loader for the real Cooja-derived event CSVs under data/processed/
=============================================================================
data/processed/ is flat: one CSV per simulation run, every label in the name

    data/processed/<a>-<b>-<honest>-<atkcount>-<c>-S<k>-exp<id>[-mobile]-<round>.csv
    e.g. 3-1-21-9-150-S2-exp5438-mobile-3.csv  -> 9 attackers, S2, mobile, round 3

  - atkcount (3/6/9)  : 4th field -- number of attacker motes in that run
  - S1..S6            : attack-type scenario
  - "-mobile"         : mobile deployment; absent = static
  - round (1/2/3)     : independent simulation repetition
Attacker mote IDs per atkcount are constant across round and environment
(data/attackers.txt):  3 -> 29,30,31   6 -> 26..31   9 -> 23..31

The static simulation is deterministic: its rounds were byte-identical, so
only static round 1 is kept in data/. Mobile rounds differ in their random
mobility realisation and are all kept.

Each CSV has the schema written by parse_serial.py:
    sim_ms,mote_id,src,R,Rhat,e,v1..v7,AC,ML,t,type,action

Labelling convention:
    y = 1  iff  src in attacker set for that file's atkcount  AND  the event is
           at or after that attacker's launch (label_start, see load_real_events)
    y = 0  otherwise
Rows observed BY an attacker mote (mote_id in attacker set) are dropped
(attackers do not run the IDS); rows where an attacker source is seen
before that attacker launches are dropped rather than
labelled benign (avoids injecting label noise from "attacker behaving
honestly pre-launch").

This loader determines atk_nodes per-file from the atkcount path segment, since
data/processed mixes 3/6/9-attacker runs together.
"""
from __future__ import annotations
import os
import re
import glob
import numpy as np
import pandas as pd

V_COLS = ["v1", "v2", "v3", "v4", "v5", "v6", "v7"]

ATK_NODES_BY_COUNT = {
    "3": frozenset({29, 30, 31}),
    "6": frozenset({26, 27, 28, 29, 30, 31}),
    "9": frozenset({23, 24, 25, 26, 27, 28, 29, 30, 31}),
}

NAME_RE = re.compile(
    r"^\d+-\d+-\d+-([369])-\d+-(S[1-6])-exp\d+(-mobile)?-(\d+)\.csv$"
)


def _parse_name(path: str):
    """-> (env, round, atkcount, scenario) from a CSV file name."""
    m = NAME_RE.match(os.path.basename(path))
    if m is None:
        raise ValueError(f"file name does not match the expected pattern: {path}")
    atkcount, scen, mobile, rnd = m.groups()
    return ("mobile" if mobile else "static"), f"r{rnd}", atkcount, scen


def load_launch_times(path: str) -> dict:
    """data/attack_launch.csv (scripts/extract_launch.py) -> {run: {mote_id: launch_ms}}."""
    tab = pd.read_csv(path)
    out = {}
    for run, grp in tab.groupby("run"):
        out[run] = dict(zip(grp["mote_id"].astype(int), grp["launch_ms"].astype(int)))
    return out


def load_real_events(csv_root: str,
                     label_start="launch",
                     launch_csv: str | None = None,
                     drop_attacker_observers: bool = True,
                     drop_prelaunch_attacker_rows: bool = True,
                     envs: tuple[str, ...] = ("mobile", "static"),
                     verbose: bool = True) -> pd.DataFrame:
    """Read every data/processed/*.csv, label every detection event, and return one
    concatenated DataFrame with columns v1..v7, y, scenario, env, round,
    atkcount, src, mote_id, t.

    label_start: "launch" (default) -- an attacker's events are attacks from its
    own [ATK-LAUNCHED] time on (sim_ms >= launch_ms, from launch_csv, default
    <csv_root>/../attack_launch.csv); a number -- a fixed start in seconds for
    every attacker (t >= label_start; 300 = the former rule).
    Observations of an attacker before its start are dropped, not labelled
    benign (drop_prelaunch_attacker_rows)."""
    # Row order seeds the stratified split, so files are read in a fixed order:
    # static first, then by round, attacker count and file name (the order the
    # former env/round/atkcount folder tree produced, so splits are unchanged).
    def order(f):
        env, rnd, atkcount, _ = _parse_name(f)
        return (env != "static", rnd, atkcount, os.path.basename(f))
    files = sorted(glob.glob(os.path.join(csv_root, "**", "*.csv"), recursive=True), key=order)
    if not files:
        raise FileNotFoundError(f"no CSVs found under {csv_root}")

    launch = None
    if str(label_start) != "launch":
        label_start = float(label_start)
    else:
        launch_csv = launch_csv or os.path.join(os.path.dirname(os.path.abspath(csv_root)),
                                                "attack_launch.csv")
        if not os.path.isfile(launch_csv):
            raise FileNotFoundError(f"{launch_csv} not found -- run scripts/extract_launch.py "
                                    f"(or pass a fixed label_start in seconds)")
        launch = load_launch_times(launch_csv)

    frames = []
    skipped_env = 0
    for fn in files:
        env, rnd, atkcount, scen = _parse_name(fn)
        if env not in envs:
            skipped_env += 1
            continue
        df = pd.read_csv(fn)
        if "type" in df.columns:
            df = df[df["type"] == "detection"].copy()
        missing = [c for c in V_COLS if c not in df.columns]
        if missing:
            raise ValueError(f"{fn}: missing columns {missing}")
        for c in V_COLS + ["t", "src", "mote_id", "sim_ms"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=V_COLS + ["t", "src", "mote_id", "sim_ms"])

        atk_nodes = ATK_NODES_BY_COUNT[atkcount]
        is_atk_src = df["src"].isin(atk_nodes)
        if drop_attacker_observers:
            df = df[~df["mote_id"].isin(atk_nodes)]
            is_atk_src = df["src"].isin(atk_nodes)
        if launch is None:
            in_window = df["t"] >= float(label_start)
        else:
            run = os.path.splitext(os.path.basename(fn))[0]
            lt = launch.get(run, {})
            absent = set(atk_nodes) - set(lt)
            if absent & set(df["src"].unique()):
                raise ValueError(f"{fn}: no launch time for attacker(s) {sorted(absent)}")
            in_window = df["sim_ms"] >= df["src"].map(lt)      # NaN (non-attacker) -> False
        df["y"] = (is_atk_src & in_window).astype(int)
        if drop_prelaunch_attacker_rows:
            df = df[~(is_atk_src & ~in_window)]

        df["scenario"] = scen
        df["env"] = env
        df["round"] = rnd
        df["atkcount"] = int(atkcount)
        frames.append(df)

    if not frames:
        raise FileNotFoundError(f"no usable CSVs under {csv_root} (envs={envs})")
    ev = pd.concat(frames, ignore_index=True)
    ev = ev.reset_index(drop=True)
    if verbose:
        print(f"[real_data] {len(files)} files ({skipped_env} skipped by env filter) "
              f"-> {len(ev)} detection events | attack={int(ev['y'].sum())} "
              f"benign={int((1 - ev['y']).sum())}")
        print("[real_data] by scenario:\n" +
              ev.groupby("scenario")["y"].agg(["count", "sum"]).to_string())
        print("[real_data] by env/round/atkcount:\n" +
              ev.groupby(["env", "round", "atkcount"])["y"].agg(["count", "sum"]).to_string())
    return ev


def features_labels(ev: pd.DataFrame):
    X = ev[V_COLS].to_numpy(dtype=np.float64)
    y = ev["y"].to_numpy(dtype=np.int8)
    groups = ev["scenario"].to_numpy()
    return X, y, groups


def compress(ev: pd.DataFrame):
    """Collapse events with the same evidence vector AND label into one weighted
    row. The fuzzy inference depends only on v1..v7, so every count-based
    quantity (confidence, support, F1, FPR, Wang-Mendel occupancy) computed on
    (X, y, w) equals the one computed on the raw events -- lossless, and about
    9x fewer rows on this corpus. Returns X (k,7), y (k,), w (k,) event counts."""
    g = ev.groupby(V_COLS + ["y"], sort=True).size().reset_index(name="w")
    return (g[V_COLS].to_numpy(dtype=np.float64), g["y"].to_numpy(dtype=np.int8),
            g["w"].to_numpy(dtype=np.int64))


def vector_ceiling(ev: pd.DataFrame):
    """Best F1 / FPR any classifier of v1..v7 alone can reach on these events:
    each distinct vector predicted as its majority label (ties -> benign).
    Identical vectors carrying both labels set this ceiling; a reported F1 at
    or above it on the same events indicates leakage, not a better rule base."""
    g = ev.groupby(V_COLS)["y"].agg(["sum", "count"])
    pos, neg = g["sum"], g["count"] - g["sum"]
    pred = pos > neg
    tp, fp, fn = pos[pred].sum(), neg[pred].sum(), pos[~pred].sum()
    f1 = 2 * tp / (2 * tp + fp + fn) if tp else 0.0
    fpr = fp / neg.sum() if neg.sum() else 0.0
    return float(f1), float(fpr)


def stratified_scenario_split(ev: pd.DataFrame, test_frac: float = 0.3,
                              seed: int = 42):
    """Chronologically-shuffled split within each S1..S6 scenario, pooling
    all env/round/atkcount combinations on both sides, so all six attack
    variants appear in both train and test."""
    rng = np.random.default_rng(seed)
    tr_idx, te_idx = [], []
    for _, grp in ev.groupby("scenario"):
        idx = grp.index.to_numpy().copy()
        rng.shuffle(idx)
        cut = int(len(idx) * (1.0 - test_frac))
        tr_idx.extend(idx[:cut])
        te_idx.extend(idx[cut:])
    return ev.loc[sorted(tr_idx)].reset_index(drop=True), \
           ev.loc[sorted(te_idx)].reset_index(drop=True)


def round_holdout_split(ev: pd.DataFrame, test_round: str = "r3"):
    """Generalisation check: hold out one entire simulation repetition
    (independent random realisation of every scenario/env/atkcount) rather
    than a resampled subset of the same runs."""
    tr = ev[ev["round"] != test_round].reset_index(drop=True)
    te = ev[ev["round"] == test_round].reset_index(drop=True)
    return tr, te


def scenario_holdout_split(ev: pd.DataFrame, test_scenario: str = "S1"):
    """Leave-one-attack-type-out: train on the other five S-variants (every
    env/round/atkcount), test on one attack type never seen during candidate
    generation or NSGA-II fitness. This is the fix reports/rules-selection-for-FERMAD.md
    (Sec. 3.4) flags as needed beyond the within-scenario random split, since
    consecutive same-run rows are autocorrelated and inflate a random-split
    test score; holding out a whole attack type removes that leakage and
    checks generalisation to attack *types*, complementing round_holdout_split
    (generalisation to an unseen simulation repetition of the SAME types)."""
    tr = ev[ev["scenario"] != test_scenario].reset_index(drop=True)
    te = ev[ev["scenario"] == test_scenario].reset_index(drop=True)
    return tr, te


def stratified_subsample(ev: pd.DataFrame, n_target: int, seed: int = 42,
                         keys=("scenario", "env", "atkcount", "round")):
    """Proportionally subsample rows within each key-combination cell,
    preserving the natural class ratio in each cell. Used to keep candidate
    generation / NSGA-II fitness evaluation tractable on ~600k-row data
    while still representing every condition; final metrics should always
    be computed on the *full* (non-subsampled) test split."""
    if n_target >= len(ev):
        return ev
    frac = n_target / len(ev)
    rng = np.random.default_rng(seed)
    parts = []
    for _, grp in ev.groupby(list(keys)):
        n = max(1, int(round(len(grp) * frac)))
        n = min(n, len(grp))
        idx = rng.choice(grp.index.to_numpy(), size=n, replace=False)
        parts.append(grp.loc[idx])
    out = pd.concat(parts, ignore_index=True)
    return out
