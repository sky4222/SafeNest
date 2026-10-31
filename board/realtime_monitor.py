"""Resident overlay, no intermediate WAV, optional bounded producer/consumer.
Not a lossless ADC streaming design: the original codec driver polls registers.
"""
from collections import deque
from datetime import datetime
from pathlib import Path
import json
import queue
import threading
import time
import wave
import numpy as np
from resident_hardware import UnifiedHardware, capture_frontend, to_pcm16, decode_audio24
from memory_model import MemoryModel
from pl_alarm import PLAlarm
from decision_rule import priority_event_decision

ROOT = Path(__file__).resolve().parent


def save_codec_wav(path, words):
    """Optional diagnostic PCM24 stereo ring file; not used by inference."""
    u = (decode_audio24(words).reshape(-1).astype(np.int64) & 0xffffff).astype(np.uint32)
    data = np.column_stack((u & 255, (u >> 8) & 255, (u >> 16) & 255)).astype(np.uint8).tobytes()
    with wave.open(str(path), 'wb') as f:
        f.setnchannels(2); f.setsampwidth(3); f.setframerate(48000); f.writeframes(data)


class RealtimeMonitor:
    def __init__(self, directory=ROOT, capture_seconds=3.0, input_source='line_in',
                 save_raw=False, alarm_callback=None, log_batch_size=10,
                 decision_threshold=0.25):
        self.directory = Path(directory).resolve()
        self.capture_seconds = float(capture_seconds)
        if not 2 <= self.capture_seconds <= 3:
            raise ValueError('Use 2..3 seconds with the existing 2-second model')
        self.runtime = self.directory / 'runtime'
        self.runtime.mkdir(exist_ok=True)
        self.save_raw = bool(save_raw)
        self.log_batch_size = int(log_batch_size)
        if self.log_batch_size < 1:
            raise ValueError('log_batch_size must be positive')
        # Validate rule before allocating/downloading hardware.
        priority_event_decision([1.0,0.0,0.0,0.0],0,decision_threshold)
        self.decision_threshold = float(decision_threshold)
        self.alarm_callback = alarm_callback
        self.model = MemoryModel(self.directory)
        tick = time.monotonic()
        self.hardware = UnifiedHardware(self.directory, input_source)
        self.startup_seconds = time.monotonic() - tick
        self.hw_alarm = PLAlarm(self.hardware.overlay)
        self.history = deque(maxlen=100)
        self.pending = []
        self.segment_id = 0
        self.dropped = 0
        self.last_processed_id = None
        self.worker = None
        self.stop_event = threading.Event()
        self.worker_error = None
        print('Overlay loaded ONCE. Initial hardware setup %.3f s' % self.startup_seconds)

    def _capture(self):
        started = time.monotonic()
        timestamp = datetime.now().isoformat(timespec='milliseconds')
        words = self.hardware.capture(self.capture_seconds)
        ended = time.monotonic()
        packet = {'words': words, 'capture_start': started, 'capture_end': ended,
                  'timestamp': timestamp, 'segment_id': self.segment_id}
        self.segment_id += 1
        return packet

    def _produce(self, output):
        try:
            while not self.stop_event.is_set():
                packet = self._capture()
                if self.stop_event.is_set():
                    break
                try:
                    output.put_nowait(packet)
                except queue.Full:
                    try:
                        output.get_nowait()
                        self.dropped += 1
                    except queue.Empty:
                        pass
                    output.put_nowait(packet)  # Only one producer.
        except BaseException as exc:
            self.worker_error = exc
            self.stop_event.set()

    def _flush(self):
        if not self.pending:
            return
        today = datetime.now().strftime('%Y-%m-%d')
        name = 'results_%s.jsonl' % today
        # Preserve original one-day log retention, only within this runtime directory.
        for path in self.runtime.glob('results_*.jsonl'):
            if path.name != name:
                path.unlink()
        with (self.runtime/name).open('a', encoding='utf-8') as f:
            for row in self.pending:
                f.write(json.dumps(row, ensure_ascii=False) + '\n')
        self.pending.clear()

    def _process(self, packet, pipelined):
        started = time.monotonic()
        tick = time.monotonic()
        samples, channel = capture_frontend(packet['words'])
        pcm = to_pcm16(samples)
        conversion_seconds = time.monotonic() - tick
        tick = time.monotonic()
        filtered = self.hardware.fir.filter_pcm(pcm)
        filter_seconds = time.monotonic() - tick
        prediction = self.model.predict_pcm(filtered)
        decision = priority_event_decision(prediction['scores'], prediction['class_id'],
                                           self.decision_threshold)
        decided_id = decision['class_id']
        decided_name = self.model.classes[decided_id]['name']
        inference_finished = time.monotonic()
        # Clear evidence across dropped observations; PL also expires it after 15 s.
        gap = self.last_processed_id is not None and packet['segment_id'] != self.last_processed_id+1
        if gap:
            self.hw_alarm.reset()
        self.last_processed_id = packet['segment_id']
        hw_state = self.hw_alarm.submit(decided_id)
        reason = 'pl_rolling_score_ge_4' if hw_state['triggered'] else None
        row = {'timestamp': packet['timestamp'], 'segment_id': packet['segment_id'],
               'pipelined': bool(pipelined), 'input_channel': channel,
               'class_id': decided_id, 'class_name': decided_name,
               'model_class_id': int(prediction['class_id']),
               'model_class_name': prediction['class_name'],
               'decision_rule': 'priority_impact_scream',
               'decision_threshold': decision['threshold'],
               'priority_applied': decision['priority_applied'],
               'decision_reason': decision['reason'],
               'scores': {item['name']: float(score) for item,score in zip(self.model.classes,prediction['scores'])},
               'capture_seconds': packet['capture_end']-packet['capture_start'],
               'capture_overrun_seconds': max(0.0,packet['capture_end']-packet['capture_start']-self.capture_seconds),
               'queue_wait_seconds': started-packet['capture_end'],
               'conversion_seconds': conversion_seconds, 'filter_seconds': filter_seconds,
               'frontend_seconds': prediction['frontend_seconds'],
               'model_seconds': prediction['model_seconds'],
               'processing_seconds': inference_finished-started,
               'capture_end_to_result_seconds': inference_finished-packet['capture_end'],
               'capture_start_to_result_seconds': inference_finished-packet['capture_start'],
               'dropped_segments_total': self.dropped,
               'discontinuous_observations': bool(gap),
               'alarm_requested': reason is not None, 'alarm_reason': reason,
               'alarm_backend': 'PL', 'rolling_score': hw_state['sum'],
               'score_window_count': hw_state['count'],
               'buzzer_active': hw_state['active'], 'alarm_cooldown': hw_state['cooldown'],
               'buzzer_muted': hw_state['muted']}
        if self.save_raw:
            save_codec_wav(self.runtime/('segment_%d.wav' % (packet['segment_id']%2)),packet['words'])
        # Diagnostic saving/logging/callback overhead excluded from latency above;
        # completion time below includes synchronous saving and callbacks.
        self.pending.append(row)
        if reason is not None:
            print('ALARM REQUESTED:', reason)
            if self.alarm_callback:
                self.alarm_callback(reason,row)
        row['processing_with_outputs_seconds'] = time.monotonic()-started
        row['capture_start_to_outputs_seconds'] = time.monotonic()-packet['capture_start']
        self.history.append(row)
        if len(self.pending) >= self.log_batch_size:
            self._flush()
        print('#%d %s | capture %.3fs | post %.3fs | CNN %.3fs | result age %.3fs | dropped %d' %
              (row['segment_id'],row['class_name'],row['capture_seconds'],
               row['processing_seconds'],row['model_seconds'],
               row['capture_end_to_result_seconds'],row['dropped_segments_total']))
        print('  PL score %d/4 | window %d/3 | triggered=%s | buzzer=%s | cooldown=%s' %
              (hw_state['sum'],hw_state['count'],hw_state['triggered'],
               hw_state['active'] and not hw_state['muted'],hw_state['cooldown']))
        if row['processing_with_outputs_seconds'] > self.capture_seconds:
            print('Processing exceeds capture interval: this board is not keeping up at this configuration.')
        return row

    def run(self, cycles=3, pipelined=False, alarm_enabled=True):
        if self.worker is not None and self.worker.is_alive():
            raise RuntimeError('Capture worker still running; do not start another monitor')
        if cycles is not None and int(cycles) <= 0:
            raise ValueError('cycles must be positive or None')
        self.hw_alarm.arm(muted=not alarm_enabled)
        self.stop_file = self.directory / "STOP_MONITOR"
        if self.stop_file.exists():
            self.hw_alarm.disarm()
            raise RuntimeError("Delete STOP_MONITOR in project folder before starting")
        self.stop_event.clear()
        self.worker_error = None
        output = queue.Queue(maxsize=2)
        if pipelined:
            self.worker = threading.Thread(target=self._produce, args=(output,), daemon=True)
            self.worker.start()
        completed = 0
        try:
            while cycles is None or completed < int(cycles):
                if self.stop_file.exists():
                    print("STOP_MONITOR detected; stopping between segments.")
                    break
                if pipelined:
                    if self.worker_error is not None:
                        raise RuntimeError('Capture worker failed') from self.worker_error
                    try:
                        packet = output.get(timeout=0.25)
                    except queue.Empty:
                        continue
                else:
                    packet = self._capture()
                self._process(packet, pipelined)
                completed += 1
        finally:
            self.hw_alarm.disarm()
            self.stop_event.set()
            if pipelined and self.worker is not None:
                # Native audio.record cannot be interrupted; wait for current segment.
                self.worker.join(timeout=self.capture_seconds*3+5)
            self._flush()
            if self.worker is not None and self.worker.is_alive():
                raise RuntimeError('Native capture did not return. Stop kernel/board before reloading PL.')
        return list(self.history)

    def close(self):
        self.hw_alarm.disarm()
        self.stop_event.set()
        if self.worker is not None and self.worker.is_alive():
            self.worker.join(timeout=self.capture_seconds*3+5)
            if self.worker.is_alive():
                raise RuntimeError('Capture still running: cannot release/reconfigure hardware')
        self._flush()
        self.hardware.close()
