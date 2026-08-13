#!/usr/bin/env python3
import csv, io, json, urllib.request, zipfile
from collections import defaultdict, Counter

GTFS='https://data.pid.cz/PID_GTFS.zip'
OUT='transit-data.json'

with urllib.request.urlopen(GTFS, timeout=60) as r:
    raw=r.read()
z=zipfile.ZipFile(io.BytesIO(raw))
def rows(name):
    with z.open(name) as f:
        return list(csv.DictReader(io.TextIOWrapper(f, encoding='utf-8-sig')))

routes=rows('routes.txt'); trips=rows('trips.txt'); stops=rows('stops.txt'); stop_times=rows('stop_times.txt')
stop_name={r['stop_id']:r['stop_name'] for r in stops}
route_info={r['route_id']:r for r in routes}
trips_by_route=defaultdict(list)
trip_meta={}
for t in trips:
    trips_by_route[t['route_id']].append(t['trip_id']); trip_meta[t['trip_id']]=t
seq=defaultdict(list)
for s in stop_times:
    seq[s['trip_id']].append((int(s['stop_sequence']),stop_name.get(s['stop_id'],s['stop_id'])))
for k in seq: seq[k]=[x[1] for x in sorted(seq[k])]

def choose_patterns(route_id):
    pats=Counter(tuple(seq[t]) for t in trips_by_route[route_id] if seq.get(t))
    by_dir={}
    for trip in trips_by_route[route_id]:
        p=tuple(seq.get(trip,[])); d=trip_meta[trip].get('direction_id','0')
        if p and (d not in by_dir or pats[p]>pats[by_dir[d]]): by_dir[d]=p
    return [list(p) for _,p in sorted(by_dir.items())]

out={'tram':{},'bus':{}}
for rid,r in route_info.items():
    short=r.get('route_short_name','').strip(); typ=r.get('route_type','')
    if typ=='0': mode='tram'
    elif typ in ('3','11') and short.isdigit() and 100<=int(short)<=299: mode='bus'
    else: continue
    patterns=choose_patterns(rid)
    if not patterns: continue
    out[mode][short]={'color':'#'+(r.get('route_color') or ('d71920' if mode=='tram' else '007ac3')),'routes':patterns}

def sortkey(x):
    return (0,int(x)) if x.isdigit() else (1,x)
out['tram']=dict(sorted(out['tram'].items(),key=lambda kv:sortkey(kv[0])))
out['bus']=dict(sorted(out['bus'].items(),key=lambda kv:sortkey(kv[0])))
with open(OUT,'w',encoding='utf-8') as f: json.dump(out,f,ensure_ascii=False,separators=(',',':'))
print('Wrote',OUT,'tram',len(out['tram']),'bus',len(out['bus']))
