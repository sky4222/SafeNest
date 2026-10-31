"""PL rolling score/buzzer interface. Never loads BaseOverlay or sleeps for beep."""
import time


class PLAlarm:
    def __init__(self, overlay):
        if 'alarm_mailbox' not in overlay.ip_dict:
            raise RuntimeError('Old overlay: rebuild and upload matching NEW bit/hwh containing alarm_mailbox')
        self.io = overlay.alarm_mailbox.mmio
        self.enabled = False
        self.muted = True
        self.toggle = 0
        self._write(0)
        self.reset()

    def _command(self, class_id=0, clear=False):
        return (int(class_id) | (self.toggle << 8) |
                (int(self.enabled) << 9) | (int(clear) << 10) |
                (int(self.muted) << 12))

    def _write(self, command):
        self.io.write(0x00, int(command))

    def status(self):
        value = int(self.io.read(0x08))
        return {'sum': value & 15, 'count': (value >> 4) & 3,
                'class_id': (value >> 6) & 3, 'active': bool(value & 256),
                'cooldown': bool(value & 512), 'triggered': bool(value & 1024),
                'accepted': (value >> 11) & 1, 'enabled': bool(value & 4096),
                'muted': bool(value & 8192), 'event_count': value >> 16}

    def _wait(self, predicate):
        deadline = time.monotonic() + 0.25
        while True:
            state = self.status()
            if predicate(state):
                return state
            if time.monotonic() >= deadline:
                self.disarm()
                raise TimeoutError('PL alarm acknowledgement timed out; check NEW bit/hwh and clock')
            time.sleep(0.0001)

    def reset(self):
        self._write(self._command(clear=True))
        self._wait(lambda s: s['count'] == 0 and s['event_count'] == 0 and
                   not s['active'] and not s['cooldown'])
        self._write(self._command())

    def arm(self, muted=False):
        self.enabled = True
        self.muted = bool(muted)
        self.reset()
        self._wait(lambda s: s['enabled'] and s['muted'] == self.muted)

    def disarm(self):
        self.enabled = False
        self._write(self._command())

    def submit(self, class_id):
        if not self.enabled:
            raise RuntimeError('Call arm() first')
        if int(class_id) not in (0, 1, 2, 3):
            raise ValueError('class_id must be 0..3')
        before = self.status()['event_count']
        self.toggle ^= 1
        self._write(self._command(class_id))
        return self._wait(lambda s: s['event_count'] == ((before + 1) & 65535)
                          and s['accepted'] == self.toggle)

    def selftest(self):
        """Real PL synthetic input test; physical buzzer muted throughout."""
        cases = [([0, 3, 0], [0, 0, 0], [False, False, False]),
                 ([2, 0, 0], [3, 3, 3], [False, False, False]),
                 ([1, 1, 0], [2, 4, 4], [False, True, False]),
                 ([2, 0, 1], [3, 3, 5], [False, False, True]),
                 ([2, 0, 0, 0], [3, 3, 3, 0], [False]*4)]
        try:
            for ids, sums, triggers in cases:
                self.arm(muted=True)
                for cid, expected, trigger in zip(ids, sums, triggers):
                    state = self.submit(cid)
                    assert state['sum'] == expected, (state, expected)
                    assert state['triggered'] == trigger, (state, trigger)
            print('PASS: real PL scoring/threshold test; buzzer was muted')
        finally:
            self.disarm()
