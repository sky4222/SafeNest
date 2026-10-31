"""Local research preprocessing. pip install numpy scipy
Run: python prepare_features.py
Produces features/train.npz, val.npz, test.npz, normalization.json.
Uses one event-centred 2-second window per file, not every background window.
Use this SAME frontend for subsequent training and inference.
"""
from pathlib import Path
from math import gcd
import csv,json,re,argparse
import numpy as np
from scipy.io import wavfile
from scipy.signal import resample_poly

FS=16000
N=32000
FFT=512
HOP=160
WIN=400
MELS=64

def waveform(path):
    fs,x=wavfile.read(str(path))
    if x.size==0:raise ValueError('Empty audio')
    if x.dtype==np.uint8:x=(x.astype(np.float64)-128)/128
    elif np.issubdtype(x.dtype,np.signedinteger):x=x.astype(np.float64)/float(-int(np.iinfo(x.dtype).min))
    elif np.issubdtype(x.dtype,np.floating):x=x.astype(np.float64)
    else:raise ValueError('Unsupported dtype')
    if not np.isfinite(x).all():raise ValueError('Nonfinite audio')
    if x.ndim==2:x=x[:,int(np.argmax(np.mean(x*x,axis=0)))]
    x=x-np.mean(x)
    if fs!=FS:
        d=gcd(int(fs),FS);x=resample_poly(x,FS//d,int(fs)//d)
    return x.astype(np.float32)

def annotation_intervals(path):
    out=[]
    if not path or not path.is_file():return out
    for line in path.read_text(errors='replace').splitlines():
        vals=re.findall(r'[-+]?(?:\d*\.\d+|\d+)(?:[eE][-+]?\d+)?',line)
        if len(vals)>=2:
            a,b=map(float,vals[:2])
            if 0<=a<b:out.append((a,b))
    return out

def event_clip(x,intervals):
    if len(x)<=N:return np.pad(x,(0,N-len(x)))
    if intervals:
        # Longest annotated event, centre its interval. Annotation is coarse.
        a,b=max(intervals,key=lambda ab:ab[1]-ab[0])
        start=int(((a+b)/2-1)*FS)
    else:
        # ESC50 has clip labels only. Select the highest-RMS complete window.
        starts=np.arange(0,len(x)-N+1,1600)
        starts=np.unique(np.append(starts,len(x)-N))
        cs=np.concatenate(([0.0],np.cumsum(x.astype(np.float64)**2)))
        start=int(starts[np.argmax(cs[starts+N]-cs[starts])])
    start=max(0,min(start,len(x)-N))
    return x[start:start+N]

def logmel(clip):
    """Fixed numeric frontend: HTK mel triangles, power, natural log."""
    clip=np.asarray(clip,np.float32)
    if len(clip)!=N:raise ValueError('Expected exactly 32000 samples')
    padded=np.pad(clip,(FFT//2,FFT//2),mode='reflect')
    frames=np.stack([padded[s:s+FFT] for s in range(0,len(padded)-FFT+1,HOP)])
    window=np.zeros(FFT)
    window[(FFT-WIN)//2:(FFT-WIN)//2+WIN]=np.hanning(WIN+1)[:-1]
    power=np.abs(np.fft.rfft(frames*window,axis=1))**2
    melmax=2595*np.log10(1+(FS/2)/700)
    points=700*(10**(np.linspace(0,melmax,MELS+2)/2595)-1)
    freqs=np.fft.rfftfreq(FFT,1/FS)
    filters=np.empty((MELS,len(freqs)))
    for m in range(MELS):
        l,c,r=points[m:m+3]
        filters[m]=np.maximum(0,np.minimum((freqs-l)/(c-l),(r-freqs)/(r-c)))
    mel=power@filters.T
    return np.log(mel.T+1e-6)[None,:,:].astype(np.float32)

def main():
    p=argparse.ArgumentParser();p.add_argument('--root',type=Path,default=Path(__file__).resolve().parent);args=p.parse_args()
    root=args.root;out=root/'features';out.mkdir(exist_ok=True)
    rows=list(csv.DictReader((root/'manifest.csv').open(encoding='utf-8-sig')))
    data={s:[] for s in ['train','val','test']}
    labels={s:[] for s in data};paths={s:[] for s in data}
    for i,row in enumerate(rows,1):
        ann=root/row['annotation_path'] if row['annotation_path'] else None
        x=waveform(root/row['path']);clip=event_clip(x,annotation_intervals(ann));f=logmel(clip)
        if f.shape!=(1,64,201):raise ValueError('Unexpected feature shape')
        s=row['split'];data[s].append(f);labels[s].append(int(row['label']));paths[s].append(row['path'])
        if i%50==0:print('Processed',i,'/',len(rows),flush=True)
    train=np.stack(data['train']);mean=float(train.mean(dtype=np.float64));std=max(float(train.std(dtype=np.float64)),1e-6)
    stats={'mean':mean,'std':std,'fit_on':'train only','sample_rate':FS,'clip_samples':N,'n_fft':FFT,'win_length':WIN,'hop_length':HOP,'n_mels':MELS,'log':'natural','window':'periodic Hann, centred in FFT','center':True,'padding':'reflect','mel':'HTK, no area normalization'}
    (out/'normalization.json').write_text(json.dumps(stats,indent=2))
    for s in data:
        x=(np.stack(data[s])-mean)/std;y=np.asarray(labels[s],np.int32)
        np.savez_compressed(out/(s+'.npz'),x=x.astype(np.float32),y=y,paths=np.asarray(paths[s]))
        print(s,x.shape,y.shape)
    print('Features prepared locally. No model has been trained.')

if __name__=='__main__':main()
