"""Convert SUMO Floating Car Data XML to V2X Nexus's JSON traffic format.

Usage:
    python tools/import_sumo_fcd.py example_fcd.xml
    python tools/import_sumo_fcd.py example_fcd.xml --out data/sumo_trace.json --limit 48

Generate FCD from an existing SUMO scenario with a small step length, e.g.
    sumo -c your_scenario.sumocfg --step-length 0.1 --fcd-output trace.xml
The dashboard assumes 100 ms per imported frame. Use 0.1 s output for consistency.
"""
import argparse
import json
import math
from pathlib import Path
from xml.etree import ElementTree as ET


def convert(input_path: Path, limit: int = 72) -> list[list[dict]]:
    raw = []
    for _, elem in ET.iterparse(input_path, events=('end',)):
        if elem.tag != 'timestep':
            continue
        vehicles=[]
        for v in elem.findall('vehicle'):
            try:
                vehicles.append({'id':str(v.attrib['id'])[:35],
                                 'x':float(v.attrib['x']), 'y':float(v.attrib['y']),
                                 'speed':float(v.attrib.get('speed','0'))*3.6,
                                 'angle':float(v.attrib.get('angle','0'))})
            except (KeyError,ValueError):
                continue
        if len(vehicles)>=3:
            raw.append(vehicles[:54])
            if len(raw)>=limit: break
        elem.clear()
    if len(raw)<8:
        raise ValueError('Need at least 8 FCD timesteps containing 3 or more vehicles')
    # Display units are mapped to a 960x540 canvas; not geographic coordinates.
    xs=[v['x'] for frame in raw for v in frame]
    ys=[v['y'] for frame in raw for v in frame]
    minx,maxx=min(xs),max(xs)
    miny,maxy=min(ys),max(ys)
    spanx=max(maxx-minx,1.0);spany=max(maxy-miny,1.0)
    scale=min(850/spanx,440/spany)
    ox=(960-spanx*scale)/2; oy=(540-spany*scale)/2
    for frame in raw:
        for v in frame:
            v['x']=round(ox+(v['x']-minx)*scale,2)
            v['y']=round(540-(oy+(v['y']-miny)*scale),2)
            # SUMO heading 0 = north, 90 = east. Canvas heading 0 = east.
            v['angle']=round(v['angle']-90,2)
            v['speed']=round(v['speed'],1)
    return raw


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('fcd_xml',type=Path)
    parser.add_argument('--out',type=Path,default=Path('data/sumo_trace.json'))
    parser.add_argument('--limit',type=int,default=48)
    args=parser.parse_args()
    result=convert(args.fcd_xml,max(8,min(72,args.limit)))
    args.out.parent.mkdir(parents=True,exist_ok=True)
    args.out.write_text(json.dumps(result,separators=(',',':')),encoding='utf-8')
    print(f'Wrote {len(result)} traffic snapshots to {args.out}')
    print('Open the V2X dashboard, select Imported SUMO Trace and Run Comparison.')


if __name__=='__main__':main()
