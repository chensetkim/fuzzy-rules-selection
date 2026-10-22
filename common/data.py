"""
data.py -- Load labelled evidence vectors from parse_serial.py event CSVs
=========================================================================
Reads every *.csv in a directory (the output of parse_serial.py: one row
per IDS event with columns sim_ms, mote_id, src, R, Rhat, e, v1..v7, AC,
ML, t, type, action), keeps `type == detection` rows, and labels each
observation with the same convention as compute_metrics.py:

    y = 1  if  src in attacker set  AND  t >= atk_start_s
    y = 0  otherwise

The attacker set is either given explicitly (--atk-nodes) or derived from
the ID convention (src >= atk_id_start).

Observations made *by* attacker motes are dropped (an attacker does not
run the IDS), and warm-up observations of attacker nodes before the attack
launches are dropped rather than labelled benign, since the ground truth of
"attacker behaving honestly pre-launch" would inject label noise.
"""

from __future__ import annotations
import os
import numpy as np
import pandas as pd

V_COLS = ["v1", "v2", "v3", "v4", "v5", "v6", "v7"]


def load_events_dir(csv_dir: str,
                    atk_nodes: set[int] | None = None,
                    atk_id_start: int = 33,
                    atk_start_s: int = 300,
                    drop_attacker_observers: bool = True,
                    drop_prelaunch_attacker_rows: bool = True) -> pd.DataFrame:
    """Return a DataFrame with columns v1..v7 (float, 0..100), y (0/1),
    scenario (from filename prefix before first '_'), plus src/mote_id/t."""
    frames = []
    for fn in sorted(os.listdir(csv_dir)):
        if not fn.endswith(".csv"):
            continue
        df = pd.read_csv(os.path.join(csv_dir, fn))
        if "type" in df.columns:
            df = df[df["type"] == "detection"].copy()
        missing = [c for c in V_COLS if c not in df.columns]
        if missing:
            raise ValueError(f"{fn}: missing columns {missing}")
        df["scenario"] = fn.split("_")[0]
        frames.append(df)
    if not frames:
        raise FileNotFoundError(f"No event CSVs found in {csv_dir}")
    ev = pd.concat(frames, ignore_index=True)

    for c in V_COLS + ["t", "src", "mote_id"]:
        ev[c] = pd.to_numeric(ev[c], errors="coerce")
    ev = ev.dropna(subset=V_COLS + ["t", "src", "mote_id"])

    if atk_nodes is not None:
        is_atk_src = ev["src"].isin(atk_nodes)
        if drop_attacker_observers:
            ev = ev[~ev["mote_id"].isin(atk_nodes)]
            is_atk_src = ev["src"].isin(atk_nodes)
    else:
        is_atk_src = ev["src"] >= atk_id_start
        if drop_attacker_observers:
            ev = ev[ev["mote_id"] < atk_id_start]
            is_atk_src = ev["src"] >= atk_id_start

    in_window = ev["t"] >= atk_start_s
    ev["y"] = (is_atk_src & in_window).astype(int)

    if drop_prelaunch_attacker_rows:
        ev = ev[~(is_atk_src & ~in_window)]

    ev = ev.reset_index(drop=True)
    return ev


def features_labels(ev: pd.DataFrame):
    X = ev[V_COLS].to_numpy(dtype=np.float64)
    y = ev["y"].to_numpy(dtype=np.int8)
    groups = ev["scenario"].to_numpy()
    return X, y, groups


def train_test_split_by_scenario(ev: pd.DataFrame, test_frac: float = 0.3,
                                 seed: int = 42):
    """Split *within* each scenario chronologically-shuffled, so every attack
    variant appears in both train and test (rule selection must see all six
    variants). Returns (train_df, test_df)."""
    rng = np.random.default_rng(seed)
    tr_idx, te_idx = [], []
    for _, grp in ev.groupby("scenario"):
        idx = grp.index.to_numpy().copy()
        rng.shuffle(idx)
        cut = int(len(idx) * (1.0 - test_frac))
        tr_idx.extend(idx[:cut])
        te_idx.extend(idx[cut:])
    return ev.loc[sorted(tr_idx)], ev.loc[sorted(te_idx)]
