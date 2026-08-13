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
trip_route={}
for t in trips:
    trips_by_route[t['route_id']].append(t['trip_id'])
    trip_meta[t['trip_id']]=t
    trip_route[t['trip_id']]=t['route_id']

# Services available at each named stop. This lets the app announce
# transfers from tram/bus stops to metro and rail without live lookups.
metro_by_stop=defaultdict(set)
rail_stops=set()
seq=defaultdict(list)
for s in stop_times:
    tid=s['trip_id']; sid=s['stop_id']; name=stop_name.get(sid,sid)
    seq[tid].append((int(s['stop_sequence']),name))
    rid=trip_route.get(tid)
    r=route_info.get(rid,{})
    typ=r.get('route_type','')
    short=r.get('route_short_name','').strip()
    if typ=='1' and short in {'A','B','C'}:
        metro_by_stop[name].add(short)
    if typ=='2':
        rail_stops.add(name)
for k in seq:
    seq[k]=[x[1] for x in sorted(seq[k])]

# A few Prague interchange names differ between surface transport and
# the corresponding metro/rail stop in GTFS, so keep explicit aliases.
METRO_ALIASES={
    'Na Knížecí':['B'],
    'Palackého náměstí':['B'],
}
RAIL_ALIASES={
    'Hlavní nádraží','Masarykovo nádraží','Nádraží Holešovice','Nádraží Vršovice',
    'Nádraží Libeň','Nádraží Vysočany','Nádraží Podbaba','Smíchovské nádraží',
    'Kačerov','Rajská zahrada','Nádraží Zahradní Město','Nádraží Hostivař',
    'Nádraží Modřany','Nádraží Klánovice','Nádraží Horní Počernice','Nádraží Radotín',
    'Nádraží Uhříněves','Nádraží Čakovice','Nádraží Kbely','Nádraží Satalice',
    'Nádraží Běchovice','Nádraží Braník','Nádraží Veleslavín'
}

def stop_obj(name):
    metro=sorted(set(metro_by_stop.get(name,set())) | set(METRO_ALIASES.get(name,[])))
    rail=(name in rail_stops) or (name in RAIL_ALIASES)
    if metro or rail:
        o={'name':name}
        if metro:o['metro']=metro
        if rail:o['rail']=True
        return o
    return name

def choose_patterns(route_id):
    pats=Counter(tuple(seq[t]) for t in trips_by_route[route_id] if seq.get(t))
    by_dir={}
    for trip in trips_by_route[route_id]:
        p=tuple(seq.get(trip,[])); d=trip_meta[trip].get('direction_id','0')
        if p and (d not in by_dir or pats[p]>pats[by_dir[d]]): by_dir[d]=p
    return [[stop_obj(name) for name in p] for _,p in sorted(by_dir.items())]

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
