"""ONE download: official codec IP + user's unchanged FIR/DMA.
No BaseOverlay import and no overlay downloads in the processing loop.
"""
from pathlib import Path
import json
import time
import xml.etree.ElementTree as ET
import numpy as np
from scipy.signal import resample_poly

ROOT = Path(__file__).resolve().parent
_FAILED_BUFFERS = []


def decode_audio24(raw):
    """PYNQ codec register words -> signed stereo 24-bit, not signed PCM32."""
    raw = np.asarray(raw)
    if raw.ndim != 1 or raw.size == 0 or raw.size % 2:
        raise ValueError('Expected nonempty interleaved stereo codec words')
    value = raw.astype(np.int64) & 0xffffff
    signed = ((value ^ 0x800000) - 0x800000).reshape(-1, 2)
    return signed


def capture_frontend(raw):
    """Exactly mirror original WAV decoding/channel/DC/resample order."""
    stereo = decode_audio24(raw).astype(np.float64) / 8388608.0
    channel = int(np.argmax(np.mean(stereo * stereo, axis=0)))
    x = stereo[:, channel]
    x = x - np.mean(x)
    x = resample_poly(x, 1, 3)  # fixed codec 48k -> training 16k; includes anti-aliasing
    return x.astype(np.float32), channel


def to_pcm16(samples):
    return np.clip(np.rint(np.asarray(samples, np.float64) * 32768),
                   -32768, 32767).astype(np.int16)


def reference(pcm, directory=ROOT):
    coeff = np.asarray(json.loads((Path(directory) / 'coefficients.json').read_text()), np.int64)
    return np.clip((np.convolve(np.asarray(pcm, np.int64), coeff)[:len(pcm)] + 16384) >> 15,
                   -32768, 32767).astype(np.int16)


class ResidentFilter:
    """Reuses physical DMA buffers; the overlay is supplied, never downloaded here."""
    def __init__(self, overlay, block=4096, timeout=10):
        from pynq import allocate
        self.dma = overlay.axi_dma_0
        self.control = overlay.filter_control.mmio
        self.block = int(block)
        if not 1 <= self.block <= 4096:
            raise ValueError('block must be 1..4096')
        self.timeout = float(timeout)
        self.failed = False
        self.closed = False
        self.tx = allocate(shape=(self.block,), dtype=np.int32)
        try:
            self.rx = allocate(shape=(self.block,), dtype=np.int32)
        except Exception:
            self.tx.freebuffer()
            raise

    def _wait(self):
        deadline = time.monotonic() + self.timeout
        while True:
            tx = self.dma.mmio.read(0x04)
            rx = self.dma.mmio.read(0x34)
            if (tx | rx) & 0x70:
                raise RuntimeError('DMA error MM2S=%08x S2MM=%08x' % (tx, rx))
            if (tx & 2) and (rx & 2):
                break
            if time.monotonic() >= deadline:
                raise TimeoutError('DMA timed out. Stop monitor; check clocks/reset/TLAST.')
            time.sleep(0.0001)
        self.dma.sendchannel.wait()
        self.dma.recvchannel.wait()  # PYNQ handles receive cache invalidation

    def run(self, pcm, bypass=False):
        pcm = np.asarray(pcm)
        if self.failed or self.closed:
            raise RuntimeError('DMA unavailable. Recover hardware before another run.')
        if pcm.ndim != 1 or not pcm.size or pcm.dtype != np.int16:
            raise ValueError('Expected nonempty PCM16 mono')
        mode = int(bypass)
        self.control.write(0, mode | 2)
        time.sleep(0.001)
        self.control.write(0, mode)
        time.sleep(0.001)  # 257-cycle history initialisation
        out = np.empty(len(pcm), np.int16)
        for start in range(0, len(pcm), self.block):
            part = pcm[start:start+self.block]
            n = len(part)
            self.tx[:n] = part
            try:
                # nbytes avoids sending stale buffer tails; MM2S produces TLAST.
                self.dma.recvchannel.transfer(self.rx, nbytes=n*4)
                self.dma.sendchannel.transfer(self.tx, nbytes=n*4)
                self._wait()
                result = np.asarray(self.rx[:n])
                if np.any(result < -32768) or np.any(result > 32767):
                    raise RuntimeError('Invalid signed PCM result')
                out[start:start+n] = result.astype(np.int16)
            except BaseException:
                self.failed = True
                _FAILED_BUFFERS.extend([self.tx, self.rx])
                raise  # Keep DMA-owned physical memory alive, including on Interrupt.
        return out

    def filter_pcm(self, pcm):
        # Same independent-recording reset and 128-sample delay compensation as before.
        raw = self.run(np.pad(pcm, (0, 128)))
        return raw[128:128+len(pcm)]

    def selftest(self, directory=ROOT):
        probe = np.random.RandomState(13).randint(-32768,32768,9000).astype(np.int16)
        np.testing.assert_array_equal(self.run(probe, True), probe)
        np.testing.assert_array_equal(self.run(probe), reference(probe, directory))
        print('PASS: DMA bypass and bit-exact FIR, including multiple DMA blocks')

    def close(self):
        if not self.closed:
            if not self.failed:
                self.tx.freebuffer()
                self.rx.freebuffer()
            self.closed = True


class UnifiedHardware:
    def __init__(self, directory=ROOT, input_source='line_in'):
        # Import registers the official PYNQ driver before Overlay discovers IPs.
        from pynq.lib.audio import AudioADAU1761
        from pynq import Overlay
        directory = Path(directory)
        bit = directory / 'safenest_audio.bit'
        hwh = bit.with_suffix('.hwh')
        if not bit.is_file() or not hwh.is_file():
            raise FileNotFoundError('Build/upload NEW safenest_audio.bit and matching .hwh')
        modules = list(ET.parse(str(hwh)).getroot().iter('MODULE'))
        names = {m.get('INSTANCE') for m in modules}
        if not {'audio_codec_ctrl_0','axi_dma_0','filter_control','alarm_mailbox'} <= names:
            raise ValueError('Old/wrong HWH: build NEW codec + FIR + alarm_mailbox bit/hwh pair')
        for m in modules:
            if m.get('INSTANCE') == 'audio_codec_ctrl_0':
                # The native PYNQ library reads the existing UIO mapping, so this matters.
                ranges = m.findall('./MEMRANGES/MEMRANGE')
                for region in ranges:
                    base = region.get('BASEVALUE')
                    if base is not None and int(base, 0) != 0x43c00000:
                        raise ValueError('Codec must remain at 0x43c00000 for stock UIO')
        if input_source not in ('line_in','microphone'):
            raise ValueError('input_source must be line_in or microphone')
        self.overlay = Overlay(str(bit), download=True)  # The ONLY download.
        self.audio = self.overlay.audio_codec_ctrl_0
        if not isinstance(self.audio, AudioADAU1761):
            raise TypeError('Official AudioADAU1761 driver did not bind; check PYNQ version')
        if self.audio.mmio.base_addr != 0x43c00000:
            raise ValueError('Codec physical address mismatch')
        # Check the installed PYNQ image's fixed UIO mapping before native C uses it.
        devices = []
        for name in Path('/sys/class/uio').glob('uio*/name'):
            if name.read_text().strip() == 'audio-codec-ctrl':
                addr = int((name.parent/'maps/map0/addr').read_text().strip(), 0)
                devices.append(addr)
        if devices != [0x43c00000]:
            raise RuntimeError('Expected existing audio-codec-ctrl UIO at 0x43c00000; found %r' % devices)
        if not Path('/dev/i2c-1').exists():
            raise RuntimeError('Existing PYNQ /dev/i2c-1 required for codec configuration')
        self.audio.configure(sample_rate=48000, iic_index=1)
        if input_source == 'line_in':
            self.audio.select_line_in()
        else:
            self.audio.select_microphone()
        self._check_status()
        self.fir = ResidentFilter(self.overlay)

    def _check_status(self):
        # Official IP status register at byte offset 16. W1C then wait for a new frame.
        self.audio.write(0x10, 1)
        deadline = time.monotonic() + 1
        while self.audio.read(0x10) == 0:
            if time.monotonic() > deadline:
                raise TimeoutError('Codec frame clock not running; check 10MHz/100MHz/I2C/audio pins')
            time.sleep(0.001)

    def capture(self, seconds=3):
        if not 0 < seconds <= 60:
            raise ValueError('Capture duration must be in (0,60]')
        self._check_status()
        self.audio.record(float(seconds))
        # Copy before a producer starts the next record (which replaces audio.buffer).
        return np.asarray(self.audio.buffer, dtype=np.int32).copy()

    def close(self):
        self.fir.close()
