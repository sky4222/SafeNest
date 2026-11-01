"""Read-only check; never programs PL. Hashes do not prove bit/HWH pairing."""
import argparse
import hashlib
import json
from pathlib import Path
import xml.etree.ElementTree as ET

def audit(bit, required=(), device=None):
    bit=Path(bit); hwh=bit.with_suffix('.hwh'); errors=[]
    if not bit.is_file() or bit.stat().st_size==0: errors.append('Missing/empty bit')
    if not hwh.is_file(): return {'ok':False,'errors':errors+['Missing HWH']}
    try: root=ET.parse(hwh).getroot()
    except ET.ParseError: return {'ok':False,'errors':errors+['Invalid HWH XML']}
    modules=list(root.iter('MODULE'))
    names={m.get('INSTANCE') for m in modules}
    names.update(m.get('FULLNAME','').strip('/') for m in modules)
    for name in required:
        if name not in names: errors.append('Missing IP: '+name)
    parts={v for e in root.iter() for k,v in e.attrib.items() if k.upper() in ('PART','DEVICE')}
    if device and device not in parts: errors.append('Target device not confirmed: '+device)
    return {'ok':not errors,'errors':errors,'devices':sorted(parts),
            'modules':sorted(n for n in names if n),
            'sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (bit,hwh) if p.is_file()},
            'limits':'Does not prove pairing, timing, pins, bit contents or hardware functionality'}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('bit')
    p.add_argument('--require-ip',action='append',default=[]); p.add_argument('--device')
    a=p.parse_args(); result=audit(a.bit,a.require_ip,a.device)
    print(json.dumps(result,indent=2)); raise SystemExit(0 if result['ok'] else 1)
