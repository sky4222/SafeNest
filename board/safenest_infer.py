"""Offline SafeNest inference on the ARM CPU, not an FPGA accelerator.

Uses the supplied training frontend unchanged. NumPy implements inference-only
Conv2d/BatchNorm/ReLU/MaxPool/global mean/Dense, with dropout disabled.
"""
from pathlib import Path
import json
import time
import numpy as np
from numpy.lib.stride_tricks import sliding_window_view
import prepare_features as frontend

ROOT = Path(__file__).resolve().parent


def conv_same(x, weight, chunk=128):
    """CHW cross-correlation, odd kernels, SAME padding and unit stride."""
    out_channels, in_channels, kh, kw = weight.shape
    if x.shape[0] != in_channels or kh % 2 != 1 or kw % 2 != 1:
        raise ValueError('Unsupported convolution shape')
    _, h, w = x.shape
    padded = np.pad(x, ((0, 0), (kh // 2, kh // 2), (kw // 2, kw // 2)))
    windows = sliding_window_view(padded, (kh, kw), axis=(1, 2))
    matrix = weight.reshape(out_channels, -1).T
    output = np.empty((h * w, out_channels), np.float32)
    # Bound the patch workspace; do not materialize the full im2col matrix.
    for start in range(0, h * w, chunk):
        indexes = np.arange(start, min(start + chunk, h * w))
        patches = windows[:, indexes // w, indexes % w, :, :]
        patches = patches.transpose(1, 0, 2, 3).reshape(len(indexes), -1)
        output[start:start + len(indexes)] = patches @ matrix
    return output.T.reshape(out_channels, h, w)


def pool2(x):
    c, h, w = x.shape
    h, w = h // 2, w // 2
    return x[:, :h * 2, :w * 2].reshape(c, h, 2, w, 2).max(axis=(2, 4))


class SafeNest:
    def __init__(self, directory=ROOT):
        directory = Path(directory)
        self.stats = json.loads((directory / 'normalization.json').read_text(encoding='utf-8'))
        self.classes = sorted(json.loads((directory / 'classes.json').read_text(encoding='utf-8')), key=lambda v: v['id'])
        if [v['id'] for v in self.classes] != list(range(4)):
            raise ValueError('This checkpoint requires exactly four ordered classes')
        for key, expected in {'sample_rate': 16000, 'clip_samples': 32000,
                              'n_fft': 512, 'win_length': 400, 'hop_length': 160,
                              'n_mels': 64, 'log': 'natural', 'center': True,
                              'padding': 'reflect', 'mel': 'HTK, no area normalization',
                              'window': 'periodic Hann, centred in FFT'}.items():
            if self.stats.get(key) != expected:
                raise ValueError('Unexpected frontend setting: ' + key)
        if not np.isfinite([self.stats['mean'], self.stats['std']]).all() or self.stats['std'] <= 0:
            raise ValueError('Invalid normalization statistics')
        with np.load(directory / 'safenest_weights.npz', allow_pickle=False) as f:
            self.weights = {key: f[key].astype(np.float32) for key in f.files}
        expected = {}
        for i, (cin, cout, k) in enumerate([(1, 32, 5), (32, 64, 5), (64, 128, 3), (128, 128, 3)], 1):
            expected['block%d.conv.weight' % i] = (cout, cin, k, k)
            for name in ['moving_mean', 'moving_variance', 'gamma', 'beta']:
                expected['block%d.bn.%s' % (i, name)] = (cout,)
        expected.update({'fc1.weight': (32, 128), 'fc1.bias': (32,),
                         'fc2.weight': (4, 32), 'fc2.bias': (4,)})
        if set(expected) != set(self.weights):
            raise ValueError('Checkpoint parameter names do not match this network')
        for name, shape in expected.items():
            if self.weights[name].shape != shape or not np.isfinite(self.weights[name]).all():
                raise ValueError('Invalid parameter: ' + name)
            if name.endswith('moving_variance') and np.any(self.weights[name] < 0):
                raise ValueError('Negative batch normalization variance')

    def logits(self, features):
        x = np.asarray(features, np.float32)
        if x.shape != (1, 64, 201) or not np.isfinite(x).all():
            raise ValueError('Expected finite features with shape (1,64,201)')
        p = self.weights
        for i in range(1, 5):
            prefix = 'block%d.' % i
            x = conv_same(x, p[prefix + 'conv.weight'])
            mean = p[prefix + 'bn.moving_mean'][:, None, None]
            var = p[prefix + 'bn.moving_variance'][:, None, None]
            gamma = p[prefix + 'bn.gamma'][:, None, None]
            beta = p[prefix + 'bn.beta'][:, None, None]
            x = (x - mean) / np.sqrt(var + np.float32(1e-5)) * gamma + beta
            x = pool2(np.maximum(x, 0))
        x = x.mean(axis=(1, 2))
        x = np.maximum(p['fc1.weight'] @ x + p['fc1.bias'], 0)
        return p['fc2.weight'] @ x + p['fc2.bias']

    def predict_wav(self, path, start_seconds=None):
        """None: training's max-energy window. Number: explicitly select 2 s."""
        tic = time.perf_counter()
        samples = frontend.waveform(path)
        if start_seconds is None:
            clip = frontend.event_clip(samples, [])
            selection = 'highest-energy 2-second window (or padded short recording)'
        else:
            if not np.isfinite(start_seconds) or start_seconds < 0:
                raise ValueError('start_seconds must be nonnegative')
            start = int(start_seconds * frontend.FS)
            if start >= len(samples):
                raise ValueError('Selected start is beyond the recording')
            clip = samples[start:start + frontend.N]
            clip = np.pad(clip, (0, frontend.N - len(clip)))
            selection = '2-second window starting at %.3f s' % start_seconds
        raw = frontend.logmel(clip)
        features = ((raw - self.stats['mean']) / self.stats['std']).astype(np.float32)
        features_seconds = time.perf_counter() - tic
        tic = time.perf_counter()
        logits = self.logits(features)
        inference_seconds = time.perf_counter() - tic
        if not np.isfinite(logits).all():
            raise ValueError('Nonfinite model output')
        scores = np.exp(logits - logits.max())
        scores /= scores.sum()
        index = int(np.argmax(scores))
        print('Selected:', selection)
        print('Prediction: %d | %s' % (index, self.classes[index]['zh']))
        for item, score in zip(self.classes, scores):
            print('  %d %-18s %.2f%%' % (item['id'], item['name'], score * 100))
        print('Frontend %.3f s; CPU model %.3f s' % (features_seconds, inference_seconds))
        print('Scores are relative softmax scores, not calibrated confidence.')
        return {'class_id': index, 'class_name': self.classes[index]['name'],
                'scores': scores, 'logits': logits, 'features': features,
                'logmel': raw, 'clip': clip, 'selection': selection}


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('wav', type=Path)
    parser.add_argument('--start', type=float, default=None)
    args = parser.parse_args()
    SafeNest().predict_wav(args.wav, args.start)
