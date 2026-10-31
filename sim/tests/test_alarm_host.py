"""No board required: Python mailbox protocol and processing/logging integration."""
import contextlib
import io
import json
from pathlib import Path
import sys
import tempfile
import types
import numpy as np
sys.path.insert(0, str(Path(__file__).resolve().parents[2]/'board'))
from pl_alarm import PLAlarm

class Mailbox:
    def __init__(self):
        self.cmd=0; self.seq=0; self.accept=0; self.window=[]
        self.last=0; self.trigger=False; self.active=False
    def write(self, offset, value):
        assert offset==0
        self.cmd=value
        toggle=(value>>8)&1
        if not value&512 or value&1024:
            self.window=[]; self.seq=0; self.accept=toggle
            self.last=0; self.trigger=False; self.active=False
        elif toggle!=self.accept:
            self.accept=toggle; self.seq=(self.seq+1)&65535
            self.last=value&3
            self.window=(self.window+[{0:0,1:2,2:3,3:0}[self.last]])[-3:]
            self.trigger=sum(self.window)>=4 and not self.active
            if self.trigger:self.active=True
    def read(self, offset):
        assert offset==8
        return (sum(self.window)|(len(self.window)<<4)|(self.last<<6)|
                (int(self.active)<<8)|(int(self.trigger)<<10)|(self.accept<<11)|
                (((self.cmd>>9)&1)<<12)|(((self.cmd>>12)&1)<<13)|(self.seq<<16))

def overlay():
    return types.SimpleNamespace(ip_dict={'alarm_mailbox':{}},
                                 alarm_mailbox=types.SimpleNamespace(mmio=Mailbox()))

alarm=PLAlarm(overlay())
alarm.selftest()
alarm.arm()
assert alarm.submit(2)['sum']==3
assert alarm.submit(1)['triggered']
alarm.disarm();assert not alarm.status()['active']
print('PASS: Python mailbox request/ack, real-driver selftest, arm/disarm against simulated registers')

import realtime_monitor as module
class FIR:
    def filter_pcm(self,x):return x
class Hardware:
    def __init__(self,*a,**kw):self.fir=FIR();self.overlay=overlay()
    def capture(self,seconds):return np.arange(960,dtype=np.int32)
    def close(self):pass
class Model:
    def __init__(self,*a,**kw):
        self.classes=[{'name':n} for n in ('normal_dialogue','impact_drop','scream_shout','footsteps')]
    def predict_pcm(self,x):
        return dict(class_id=0,class_name='normal_dialogue',scores=np.array([.60,.05,.30,.05]),
                    frontend_seconds=.001,model_seconds=.002)
module.UnifiedHardware=Hardware;module.MemoryModel=Model
with tempfile.TemporaryDirectory() as folder:
    with contextlib.redirect_stdout(io.StringIO()) as output:
        monitor=module.RealtimeMonitor(folder,input_source='microphone',log_batch_size=1)
        rows=monitor.run(cycles=2,pipelined=False)
    assert [r['class_name'] for r in rows]==['scream_shout']*2
    assert [r['model_class_name'] for r in rows]==['normal_dialogue']*2
    assert [r['rolling_score'] for r in rows]==[3,6]
    assert [r['alarm_requested'] for r in rows]==[False,True]
    assert all(r['alarm_backend']=='PL' for r in rows)
    assert not monitor.hw_alarm.status()['active']
    logs=[json.loads(x) for p in (Path(folder)/'runtime').glob('*.jsonl') for x in p.read_text().splitlines()]
    assert logs[-1]['rolling_score']==6 and logs[-1]['alarm_requested']
    assert 'PL score 6/4' in output.getvalue()
    # Stop file is checked before capture and leaves the output disabled.
    (Path(folder)/'STOP_MONITOR').touch()
    try:monitor.run(cycles=1)
    except RuntimeError:pass
    else:raise AssertionError('Existing stop file must prevent run')
    assert not monitor.hw_alarm.status()['enabled']
print('PASS: actual run/_process uses PL mailbox, logs new rule/score/trigger; finalization disarms; stop file honored')
