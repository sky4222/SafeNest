"""Apply the updated _process method to an idle existing monitor, without reload of PL."""
import importlib
import types


def apply_to_monitor(monitor,threshold=0.25):
    worker=getattr(monitor,'worker',None)
    if worker is not None and worker.is_alive():
        raise RuntimeError('Capture worker is still alive. Wait for interrupt/stop to finish.')
    hardware=getattr(monitor,'hardware',None)
    if hardware is None:
        raise TypeError('Expected the new RealtimeMonitor, not old SafeNestMonitor')
    if getattr(hardware.fir,'closed',False) or getattr(hardware.fir,'failed',False):
        raise RuntimeError('Hardware was closed or DMA failed; cannot reuse this monitor')
    import decision_rule
    import realtime_monitor
    importlib.reload(decision_rule)
    module=importlib.reload(realtime_monitor)
    decision_rule.priority_event_decision([1.,0.,0.,0.],0,threshold)
    monitor.decision_threshold=float(threshold)
    monitor._process=types.MethodType(module.RealtimeMonitor._process,monitor)
    print('Updated result rule: impact or scream > %.2f%%; choose the higher of them.'%(100*threshold))
    print('Model scores are retained. Original class is saved in model_class_id/model_class_name.')
    print('Overlay and weights were not reloaded. Existing alarm policy remains active.')
