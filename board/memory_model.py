"""Original model/weights/frontend, with an in-memory entry point."""
import time
import numpy as np
import prepare_features as frontend
from safenest_infer import SafeNest


class MemoryModel(SafeNest):
    def predict_pcm(self, pcm):
        pcm = np.asarray(pcm)
        if pcm.dtype != np.int16 or pcm.ndim != 1 or not pcm.size:
            raise ValueError('Expected nonempty mono PCM16 at 16kHz')
        tick = time.perf_counter()
        # Same conversion and DC removal as waveform(filtered.wav), without a WAV.
        x = pcm.astype(np.float64) / 32768.0
        x = (x - x.mean()).astype(np.float32)
        clip = frontend.event_clip(x, [])
        raw = frontend.logmel(clip)
        features = ((raw - self.stats['mean']) / self.stats['std']).astype(np.float32)
        frontend_seconds = time.perf_counter() - tick
        tick = time.perf_counter()
        logits = self.logits(features)
        model_seconds = time.perf_counter() - tick
        if not np.isfinite(logits).all():
            raise ValueError('Nonfinite logits')
        scores = np.exp(logits - logits.max())
        scores /= scores.sum()
        index = int(np.argmax(scores))
        return {'class_id': index, 'class_name': self.classes[index]['name'],
                'scores': scores, 'logits': logits, 'features': features,
                'selection': 'training highest-energy 2-second window, or padded short input',
                'frontend_seconds': frontend_seconds, 'model_seconds': model_seconds}
