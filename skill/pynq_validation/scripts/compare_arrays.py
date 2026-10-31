"""Compare already-aligned .npy reference and accelerator results."""
import argparse
import json
import numpy as np

def compare(x,y,atol=0,rtol=0):
    x,y=np.asarray(x),np.asarray(y)
    if not np.isfinite([atol,rtol]).all() or min(atol,rtol)<0: raise ValueError('Invalid tolerances')
    if x.shape!=y.shape or not x.size: raise ValueError('Nonempty equal shapes required')
    if x.dtype.kind not in 'iuf' or y.dtype.kind not in 'iuf': raise ValueError('Real numeric arrays required')
    if not np.isfinite(x).all() or not np.isfinite(y).all(): raise ValueError('NaN/Inf rejected')
    if max(np.max(np.abs(x.astype(object))),np.max(np.abs(y.astype(object))))>2**53:
        raise ValueError('Values above 2**53 need an exact integer comparator')
    x,y=x.astype(np.float64),y.astype(np.float64); delta=np.abs(x-y)
    bad=delta>atol+rtol*np.abs(x)
    return {'ok':not bool(bad.any()),'shape':list(x.shape),'max_abs_error':float(delta.max()),
            'mismatch_count':int(bad.sum()),'atol':atol,'rtol':rtol}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__); p.add_argument('reference'); p.add_argument('actual')
    p.add_argument('--atol',type=float,default=0); p.add_argument('--rtol',type=float,default=0)
    a=p.parse_args(); result=compare(np.load(a.reference,allow_pickle=False),np.load(a.actual,allow_pickle=False),a.atol,a.rtol)
    print(json.dumps(result,indent=2)); raise SystemExit(0 if result['ok'] else 1)
