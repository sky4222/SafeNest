"""Host-only functional regression; does NOT validate Vivado or the board."""
from pathlib import Path
import contextlib, io, json, sys, tempfile, types, wave
import numpy as np
from scipy.io import wavfile
ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'board'))
from resident_hardware import capture_frontend, decode_audio24, reference, ResidentFilter
from realtime_monitor import save_codec_wav
from memory_model import MemoryModel
import prepare_features as frontend

rng = np.random.RandomState(2026)
with tempfile.TemporaryDirectory() as temp:
    temp = Path(temp)
    signed = rng.randint(-8388608,8388608,size=(144000,2))
    signed[:,1] //= 4
    words = (signed.reshape(-1)&0xffffff).astype(np.int32)
    np.testing.assert_array_equal(decode_audio24(words),signed)
    save_codec_wav(temp/'raw.wav',words)
    samples, channel = capture_frontend(words)
    assert channel == 0
    np.testing.assert_array_equal(samples,frontend.waveform(temp/'raw.wav'))
    print('PASS: codec PCM24 stereo -> memory frontend equals original WAV frontend')
    model = MemoryModel(ROOT/'board')
    for n in [16000,32000,48000]:
        pcm = rng.randint(-8000,8001,n).astype(np.int16)
        wavfile.write(str(temp/'filtered.wav'),16000,pcm)
        a = model.predict_pcm(pcm)
        with contextlib.redirect_stdout(io.StringIO()):
            b = model.predict_wav(temp/'filtered.wav')
        for key in ['features','logits','scores']:
            np.testing.assert_array_equal(a[key],b[key])
    print('PASS: memory features/logits/scores exactly equal original WAV path (1/2/3 s)')

# A software DMA emulator exercises physical-buffer lifecycle, chunk sizes and resets.
# It is not an AXI protocol/timing simulation.
class Buffer(np.ndarray):
    def freebuffer(self): self.freed=True
allocations=[]
def allocate(shape,dtype):
    x=np.zeros(shape,dtype=dtype).view(Buffer);x.freed=False
    allocations.append(x);return x
sys.modules['pynq']=types.SimpleNamespace(allocate=allocate)
coeff=np.array(json.loads((ROOT/'board/coefficients.json').read_text()),np.int64)
class Control:
    def __init__(self):self.history=np.zeros(256,np.int64);self.bypass=0
    def write(self,offset,value):
        if value&2:self.history[:]=0
        self.bypass=value&1
control=Control()
class Channel:
    def __init__(self,receive):self.receive=receive;self.counts=[]
    def transfer(self,buf,nbytes):
        self.counts.append(nbytes)
        n=nbytes//4
        if self.receive:self.destination=buf;self.n=n;return
        assert receiver.n==n
        pcm=np.asarray(buf[:n],np.int64)
        if control.bypass: y=pcm
        else:
            data=np.concatenate([control.history,pcm])
            y=np.clip((np.convolve(data,coeff)[256:256+n]+16384)>>15,-32768,32767)
            control.history=data[-256:].copy()
        receiver.destination[:n]=y
    def wait(self):pass
receiver=Channel(True);sender=Channel(False)
dma=types.SimpleNamespace(sendchannel=sender,recvchannel=receiver,mmio=types.SimpleNamespace(read=lambda offset:2))
ol=types.SimpleNamespace(axi_dma_0=dma,filter_control=types.SimpleNamespace(mmio=control))
hw=ResidentFilter(ol)
for n in [1,4096,8193,48000]:
    x=rng.randint(-32768,32768,n).astype(np.int16)
    np.testing.assert_array_equal(hw.run(x,True),x)
    np.testing.assert_array_equal(hw.run(x),reference(x,ROOT/'board'))
assert len(allocations)==2
assert all(0<n<=4096*4 for n in sender.counts)
hw.close()
assert all(x.freed for x in allocations)
print('PASS: resident-buffer reuse, bypass/FIR equality and partial-last-block byte lengths')
print('HOST REGRESSION PASSED; physical PYNQ/Vivado tests remain required.')

# Scheduler integration: resident hardware instance, finite queue and orderly stop.
import realtime_monitor as monitor_module
import time
class FakeFIR:
    def filter_pcm(self,x):return x
class FakeHardware:
    loads=0
    def __init__(self,*a,**kw):
        FakeHardware.loads+=1;self.fir=FakeFIR();self.closed=False;self.overlay=object()
    def capture(self,seconds):
        time.sleep(.003)
        return np.arange(480,dtype=np.int32)
    def close(self):self.closed=True
class FakeModel:
    def __init__(self,*a):self.classes=[{'name':str(i)} for i in range(4)]
    def predict_pcm(self,pcm):
        time.sleep(.02)
        return {'class_id':0,'class_name':'normal_dialogue','scores':np.array([.9,.03,.03,.04]),
                'frontend_seconds':.001,'model_seconds':.019}
monitor_module.UnifiedHardware=FakeHardware
monitor_module.MemoryModel=FakeModel
class FakeAlarm:
    def __init__(self,overlay):pass
    def arm(self,muted=False):self.muted=muted
    def disarm(self):pass
    def reset(self):pass
    def submit(self,cid):
        return dict(sum=0,count=1,triggered=False,active=False,cooldown=False,muted=self.muted)
monitor_module.PLAlarm=FakeAlarm
with tempfile.TemporaryDirectory() as temp:
    with contextlib.redirect_stdout(io.StringIO()):
        monitor=monitor_module.RealtimeMonitor(temp)
        monitor.run(cycles=2,pipelined=False)
        monitor.run(cycles=5,pipelined=True)
        monitor.close()
    assert FakeHardware.loads==1
    assert monitor.dropped>0 and not monitor.worker.is_alive()
    assert len(monitor.history)==7
    rows=[json.loads(line) for p in (Path(temp)/'runtime').glob('*.jsonl') for line in p.read_text().splitlines()]
    assert len(rows)==7
    assert all(r['capture_end_to_result_seconds']>=0 for r in rows)
print('PASS: one hardware initialization across sequential/pipeline runs, bounded queue drops reported, logs flushed, capture worker stopped')
