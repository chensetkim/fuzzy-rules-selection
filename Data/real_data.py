"""
real_data.py -- Loader for the real Cooja-derived event CSVs under Data/csv/
=============================================================================
Data/csv/ layout (note: the static branch is literally named " static" with
a leading space -- an artefact of how the folder was created upstream; this
loader does not depend on that quirk since it walks the tree and infers the
environment tag from a regex, but callers should not assume Path("static")
exists verbatim):

    Data/csv/{mobile,<static-dir>}/r{1,2,3}/{3,6,9}/<sim-id>-S<k>-exp<id>[-mobile]-<round>.csv

  - mobile / static  : deployment scenario (env)
  - r1 / r2 / r3      : independent simulation repetitions (round)
  - 3 / 6 / 9         : number of attacker motes in that run (atkcount)
  - S1..S6            : attack-type scenario embedded in the filename
  - attacker-id.txt (or attack-id.txt) in each round dir / env dir maps
    atkcount -> comma-separated attacker mote IDs. In this dataset the
    mapping is constant across round and environment:
        3 -> 29,30,31        6 -> 26..31        9 -> 23..31

Each CSV has the schema written by parse_serial.py:
    sim_ms,mote_id,src,R,Rhat,e,v1..v7,AC,ML,t,type,action

Labelling convention (same as CARS/rs/data.py / compute_metrics.py):
    y = 1  iff  src in attacker set for that file's atkcount  AND  t >= atk_start_s
    y = 0  otherwise
Rows observed BY an attacker mote (mote_id in attacker set) are dropped
(attackers do not run the IDS); rows where an attacker source is seen
before the attack launches (t < atk_start_s) are dropped rather than
labelled benign (avoids injecting label noise from "attacker behaving
honestly pre-launch").

Unlike CARS/rs/data.py (single atk_nodes for a whole directory), this
loader determines atk_nodes per-file from the atkcount path segment, since
Data/csv mixes 3/6/9-attacker runs together.
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

PATH_RE = re.compile(
    r"/(mobile|static)/r(\d)/([369])/[^/]*-(S[1-6])-exp\d+.*\.csv$"
)


def _parse_path(path: str):
    m = PATH_RE.search(path.replace(" static", "/static").replace("//", "/"))
    if m is None:
        # fall back: normalise any amount of stray whitespace around 'static'
        norm = re.sub(r"/\s*static/", "/static/", path)
        m = PATH_RE.search(norm)
    if m is None:
        raise ValueError(f"path does not match expected layout: {path}")
    env, rnd, atkcount, scen = m.groups()
    return env, f"r{rnd}", atkcount, scen


def load_real_events(csv_root: str,
                     atk_start_s: int = 300,
                     drop_attacker_observers: bool = True,
                     drop_prelaunch_attacker_rows: bool = True,
                     envs: tuple[str, ...] = ("mobile", "static"),
                     dedup_static_rounds: bool = True,
                     verbose: bool = True) -> pd.DataFrame:
    """Walk Data/csv/**/*.csv, label every detection event, and return one
    concatenated DataFrame with columns v1..v7, y, scenario, env, round,
    atkcount, src, mote_id, t.

    dedup_static_rounds: the static branch is a deterministic simulation
    (no mobility randomness), so Data/csv/ static/r1, r2, r3 contain
    byte-identical CSVs per scenario/atkcount (verified by hashing every
    file). Loading all three would silently triple-count every static row
    and bias support/confidence statistics + train/test balance. When True
    (default), only static/r1 is loaded; static/r2 and r3 are skipped.
    Mobile rounds ARE independent (mobility is stochastic) and are always
    loaded in full.
    """
    files = sorted(glob.glob(os.path.join(csv_root, "**", "*.csv"), recursive=True))
    if not files:
        raise FileNotFoundError(f"no CSVs found under {csv_root}")

    frames = []
    skipped_env = 0
    skipped_dup = 0
    for fn in files:
        env, rnd, atkcount, scen = _parse_path(fn)
        if env not in envs:
            skipped_env += 1
            continue
        if dedup_static_rounds and env == "static" and rnd != "r1":
            skipped_dup += 1
            continue
        df = pd.read_csv(fn)
        if "type" in df.columns:
            df = df[df["type"] == "detection"].copy()
        missing = [c for c in V_COLS if c not in df.columns]
        if missing:
            raise ValueError(f"{fn}: missing columns {missing}")
        for c in V_COLS + ["t", "src", "mote_id"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.dropna(subset=V_COLS + ["t", "src", "mote_id"])

        atk_nodes = ATK_NODES_BY_COUNT[atkcount]
        is_atk_src = df["src"].isin(atk_nodes)
        if drop_attacker_observers:
            df = df[~df["mote_id"].isin(atk_nodes)]
            is_atk_src = df["src"].isin(atk_nodes)
        in_window = df["t"] >= atk_start_s
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
        print(f"[real_data] {len(files)} files ({skipped_env} skipped by env filter, "
              f"{skipped_dup} skipped as duplicate static rounds) "
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


def stratified_scenario_split(ev: pd.DataFrame, test_frac: float = 0.3,
                              seed: int = 42):
    """Chronologically-shuffled split within each S1..S6 scenario, pooling
    all env/round/atkcount combinations on both sides (matches the
    CARS/rs/data.py convention: all six attack variants appear in both
    train and test)."""
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
    generation or NSGA-II fitness. This is the fix CARS/fuzzy_rules_selection.md
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
