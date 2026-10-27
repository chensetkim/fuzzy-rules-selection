#!/usr/bin/env python3
"""New inspection of retained artifacts; never runs optimisation or simulations."""
from pathlib import Path
import csv, re, hashlib, sys, json
HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
FW = ROOT.parent / 'DM-2H-FuzzRID-Contiki-OS-3.0/apps/2h-fuzzrid/fuzzrid-fuzzy.c'
OUT = HERE / 'evidence'
OUT.mkdir(exist_ok=True)
used = {HERE/'applied-33-fuzzy-rules.txt', FW, Path(__file__).resolve()}
def write(name, rows):
    with (OUT/name).open('w', newline='') as f:
        w=csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
def canon(s):
    return re.sub(r'\s+', ' ', s.strip()).replace('(', '').replace(')', '')
def expr(s):
    s=s.strip()
    m=re.fullmatch(r'mu_(L|M|H|not_H)\(v([1-7])\)',s)
    if m: return f'v{m[2]} is {m[1].replace("not_H", "not-H")}'
    m=re.fullmatch(r'(min2|max2)\((.*)\)',s)
    if not m: raise ValueError(s)
    depth=0
    for i,c in enumerate(m[2]):
        depth += (c=='(')-(c==')')
        if c==',' and depth==0:
            op=' AND ' if m[1]=='min2' else ' OR '
            return '('+expr(m[2][:i])+op+expr(m[2][i+1:])+')'
    raise ValueError(s)
reference={int(n):(canon(c),int(z)) for n,c,z in re.findall(r'^(\d+)\tIF (.*?) THEN AC = (\d+)',(HERE/'applied-33-fuzzy-rules.txt').read_text(),re.M)}
src=FW.read_text(); body=src[src.index('\nfuzzrid_fuzzy_r33_infer_ac_flat('):]
rows=[]
for m in re.finditer(r'w\[(\d+)\]\s*=\s*(.*?);\s*zc\[\1\]\s*=\s*(\d+);',body):
    n=int(m[1]); condition=canon(expr(m[2])); z=int(m[3]); line=src[:src.index(body)+m.start()].count('\n')+1
    rows.append(dict(rule=n,listed_condition=reference[n][0],firmware_condition=condition,listed_singleton=reference[n][1],firmware_singleton=z,match=(reference[n]==(condition,z)),source_line=line))
assert len(reference)==len(rows)==33
write('rule_correspondence.csv',rows)
inventory=[]
for p in sorted((ROOT/'outputs').rglob('selected_rules*.txt')):
    used.add(p); text=p.read_text(); rules=[]
    for c,z in re.findall(r'IF (.*?) THEN AC = (?:VL|VH|L|M|H) \((\d+)\)',text): rules.append((canon(c),int(z)))
    matched=sum(x in rules for x in reference.values())
    inventory.append(dict(file=str(p.relative_to(ROOT)),parsed_rules=len(rules),matching_reference_rules=matched,exact_33_rule_set=(len(rules)==33 and set(rules)==set(reference.values()))))
write('selection_output_inventory.csv',inventory)
for p in [ROOT/'run_cars.sh',ROOT/'common/real_data.py',ROOT/'common/optimize.py',ROOT/'methods/cars/run_real_selection.py',ROOT/'methods/cars/finalize_selection.py']:
    used.add(p)
    (OUT/(p.name+'.snapshot.txt')).write_text(p.read_text())
run=ROOT/'outputs/cars/run_full_seed42'
for p in [run/'config.txt',run/'SUMMARY.md',run/'seed_42/logs/select.log']:
    used.add(p); (OUT/('retained_'+p.name)).write_bytes(p.read_bytes())
# Reconstruct current data allocation with the current loader, not historical provenance.
sys.path.insert(0,str(ROOT/'common'))
from real_data import load_real_events, stratified_scenario_split, round_holdout_split
ev=load_real_events(str(ROOT/'data/processed'),label_start='launch',verbose=False)
# Loader omits filenames: use the explicit scenario/environment/round/attacker-count group.
ev['run'] = ev[['scenario','env','round','atkcount']].astype(str).agg('/'.join,axis=1)
counts=[]; members=[]; overlaps=[]
for split, pair in [('primary',stratified_scenario_split(ev,test_frac=.3,seed=42)),('round_holdout',round_holdout_split(ev))]:
    for part, frame in zip(['train','test'],pair):
        counts.append(dict(split=split,partition=part,events=len(frame),attack=int(frame.y.sum()),benign=int((frame.y==0).sum())))
        for runid,g in frame.groupby('run'):
            members.append(dict(split=split,partition=part,run=runid,events=len(g),attack=int(g.y.sum()),benign=int((g.y==0).sum())))
    common=set(pair[0]['run']) & set(pair[1]['run'])
    overlaps.append(dict(split=split,shared_run_ids=len(common),run_ids=sorted(common)))
write('development_counts.csv',counts); write('allocation_manifest.csv',members)
(OUT/'split_separation_check.json').write_text(json.dumps(overlaps,indent=2)+'\n')
used.update((ROOT/'data/processed').rglob('*.csv'))
used.update([ROOT/'data/attack_launch.csv',ROOT/'data/attackers.txt'])
write('artifact_hashes.csv',[dict(path=str(p),bytes=p.stat().st_size,sha256=hashlib.sha256(p.read_bytes()).hexdigest()) for p in sorted(used) if p.is_file()])
print(json.dumps(dict(firmware_matches=sum(r['match'] for r in rows),outputs_inspected=len(inventory),exact_saved_matches=sum(r['exact_33_rule_set'] for r in inventory),counts=counts,shared_run_ids=[(r['split'],r['shared_run_ids']) for r in overlaps]),indent=2))
