import sys
import tempfile
from pathlib import Path
import numpy as np
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from check_overlay import audit
from compare_arrays import compare
with tempfile.TemporaryDirectory() as tmp:
    b=Path(tmp)/'example.bit'; assert not audit(b)['ok']; b.write_bytes(b'fixture only')
    h=b.with_suffix('.hwh'); h.write_text('<SYSTEM><DEVICE PART="other_board"/><MODULE INSTANCE="dma"/></SYSTEM>')
    assert audit(b,['dma'],'other_board')['ok']
    assert not audit(b,['missing'])['ok']; assert not audit(b,device='wrong')['ok']
    h.write_text('<broken'); assert not audit(b)['ok']
assert compare([1,2],[1,2])['ok']; assert not compare([1,2],[1,3])['ok']
assert compare([1.],[1.001],atol=.01)['ok']
for x,y in [([1],[1,2]),([np.nan],[1]),([1],[np.inf]),([2**54],[2**54])]:
    try: compare(x,y)
    except ValueError: pass
    else: raise AssertionError('Expected rejection')
print('PASS: metadata fixtures and reference comparator; no physical board used')
