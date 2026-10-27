#!/usr/bin/env python3
"""Read-only Git recovery: export existing committed records, never invent history."""
from pathlib import Path
import subprocess, csv, re, hashlib, json
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
OUT=HERE/'evidence/history'; OUT.mkdir(parents=True,exist_ok=True)
def git(repo,*args):
    return subprocess.check_output(['git','-C',str(repo),*args])
def write(name, rows, fields):
    with (OUT/name).open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(rows)
def norm(s): return re.sub(r'\s+',' ',s.strip()).replace('(','').replace(')','')
ref={(norm(c),int(z)) for c,z in re.findall(r'^\d+\tIF (.*?) THEN AC = (\d+)',(HERE/'applied-33-fuzzy-rules.txt').read_text(),re.M)}
rows=[]; seen=set(); commits=git(ROOT,'rev-list','--all').decode().splitlines()
for commit in commits:
    paths=git(ROOT,'ls-tree','-r','--name-only',commit).decode().splitlines()
    for path in paths:
        if not re.search(r'selected_rules[^/]*\.txt$',path):continue
        blob=git(ROOT,'rev-parse',commit+':'+path).decode().strip()
        if (path,blob) in seen: continue
        seen.add((path,blob))
        data=git(ROOT,'show',commit+':'+path)
        rules=[(norm(c),int(z)) for c,z in re.findall(r'IF (.*?) THEN AC = (?:VL|VH|L|M|H) \((\d+)\)',data.decode())]
        exact=len(rules)==33 and set(rules)==ref
        rows.append(dict(commit=commit,path=path,blob=blob,parsed_rules=len(rules),matching_reference_rules=len(ref & set(rules)),exact_33_rule_set=exact))
        if exact:(OUT/('selected_33_'+blob+'.txt')).write_bytes(data)
write('committed_selection_inventory.csv',rows,['commit','path','blob','parsed_rules','matching_reference_rules','exact_33_rule_set'])
fwrepo=ROOT.parent/'DM-2H-FuzzRID-Contiki-OS-3.0'; path='apps/2h-fuzzrid/fuzzrid-fuzzy.c'
fwrows=[]
for commit in git(fwrepo,'rev-list','--all','--',path).decode().splitlines():
    try: data=git(fwrepo,'show',commit+':'+path)
    except subprocess.CalledProcessError:continue
    if b'\nfuzzrid_fuzzy_r33_infer_ac_flat(' not in data:continue
    meta=git(fwrepo,'show','-s','--format=%aI%n%cI%n%s',commit).decode().splitlines()
    current=(fwrepo/path).read_bytes()
    fwrows.append(dict(commit=commit,author_date=meta[0],committer_date=meta[1],subject=meta[2],sha256=hashlib.sha256(data).hexdigest(),entire_file_matches_current=data==current))
    (OUT/('firmware_'+commit+'.c')).write_bytes(data)
write('firmware_history.csv',fwrows,['commit','author_date','committer_date','subject','sha256','entire_file_matches_current'])
for repo,name in [(ROOT,'selection'),(fwrepo,'firmware')]:
    (OUT/(name+'_git_log.txt')).write_bytes(git(repo,'log','--all','--format=fuller','--date=iso-strict'))
summary=dict(selection_commits_scanned=len(commits),unique_path_blob_rule_listings=len(rows),exact_33_rule_matches=sum(r['exact_33_rule_set'] for r in rows),firmware_versions_with_r33=len(fwrows))
(OUT/'recovery_summary.json').write_text(json.dumps(summary,indent=2)+'\n')
print(json.dumps(summary,indent=2))
