"""Synthetic events CSVs in parse_serial.py schema for a smoke test."""
import numpy as np, pandas as pd, os
rng = np.random.default_rng(7)
os.makedirs("synth_csv", exist_ok=True)
COLS = "sim_ms,mote_id,src,R,Rhat,e,v1,v2,v3,v4,v5,v6,v7,AC,ML,t,type,action".split(",")

def benign(n):
    v = rng.beta(1.2, 8, (n,7))*100          # mostly low evidence
    v[:, 5] = rng.beta(2, 4, n)*100          # v6 mobility varies more
    return v

def attack(n, kind):
    v = rng.beta(1.2, 8, (n,7))*100
    if kind == 1: v[:,0] = rng.uniform(70,100,n)                       # jump: v1 high
    if kind == 2: v[:,2] = rng.uniform(65,100,n); v[:,1]=rng.uniform(50,95,n)  # slow: CUSUM+trickle
    if kind == 3: v[:,3] = rng.uniform(65,100,n); v[:,1]=rng.uniform(50,95,n)  # drift
    if kind == 4: v[:,2] = rng.uniform(55,90,n); v[:,4]=rng.uniform(55,95,n)   # slow probe
    if kind == 5: v[:,4] = rng.uniform(70,100,n); v[:,1]=rng.uniform(55,95,n)  # fluctuation
    if kind == 6: v[:,6] = rng.uniform(70,100,n)                       # forge 2hop: v7
    v[:,5] = rng.beta(1.5,6,n)*100           # low MI mostly
    return v

for s in range(1,7):
    rows=[]
    for run in range(1,4):
        # honest observations (pre+post window), observers 3..30, srcs 3..30
        for _ in range(400):
            t = rng.integers(60, 1800); vv = benign(1)[0]
            rows.append([t*1000, rng.integers(3,31), rng.integers(3,31), 300,300,0,
                         *np.round(vv).astype(int), 0,0,t,"detection",""])
        # attacker observations by honest motes, src >= 33, t >= 300
        for _ in range(150):
            t = rng.integers(300, 1800); vv = attack(1, s)[0]
            rows.append([t*1000, rng.integers(3,31), rng.integers(33,36), 260,510,-250,
                         *np.round(vv).astype(int), 0,0,t,"detection",""])
    pd.DataFrame(rows, columns=COLS).to_csv(f"synth_csv/S{s}_all.csv", index=False)
print("synthetic CSVs written")
