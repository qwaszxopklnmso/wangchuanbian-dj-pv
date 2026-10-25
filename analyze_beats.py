# -*- coding: utf-8 -*-
"""节拍分析：频谱通量 + 自相关测速 + 相位拟合
产出: assets/grid.json (beat0/period/bpm), assets/beats.npy, assets/flux*.npy
依赖: assets/audio_mono.wav (由 忘川彼岸DJ名龙.m4s 转出, 见 README)
"""
import json, os
import numpy as np
from scipy.io import wavfile
from scipy.signal import stft

ROOT = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(ROOT, 'assets')
os.makedirs(A, exist_ok=True)

sr, y = wavfile.read(os.path.join(A, 'audio_mono.wav'))
y = y.astype(np.float64) / 32768.0
dur = len(y) / sr

n_fft, hop = 1024, 256
f, t, Z = stft(y, fs=sr, nperseg=n_fft, noverlap=n_fft - hop, padded=False, boundary=None)
S = np.abs(Z)

# 全频段 + 低频(底鼓)频谱通量
flux = np.maximum(0, np.diff(S, axis=1)).sum(axis=0)
flux_low = np.maximum(0, np.diff(S[f < 130], axis=1)).sum(axis=0)
flux /= (flux.max() + 1e-9)
flux_low /= (flux_low.max() + 1e-9)
tf = t[1:]
sr_hop = sr / hop


def estimate_period(env, bpm_lo=85, bpm_hi=180):
    x = env - env.mean()
    n = len(x)
    ac = np.correlate(x, x, 'full')[n - 1:n + int(sr_hop * 60 / bpm_lo)]
    lags = np.arange(len(ac)) / sr_hop
    ok = (lags >= 60 / bpm_hi) & (lags <= 60 / bpm_lo)
    return float(lags[np.argmax((ac / (ac[0] + 1e-9)) * ok)])


def fit_phase(env, period):
    best = None
    for off in np.linspace(0, period, 800):
        grid = np.arange(off, dur, period)
        idx = np.clip((grid * sr_hop).astype(int), 0, len(env) - 1)
        v = env[idx].mean()
        if best is None or v > best[0]:
            best = (v, off)
    return float(best[1])


period = estimate_period(flux_low)
beat0 = fit_phase(flux_low, period)
bpm = 60.0 / period
beats = np.arange(beat0, dur + period, period)

np.save(os.path.join(A, 'beats.npy'), beats)
np.save(os.path.join(A, 'flux.npy'), flux)
np.save(os.path.join(A, 'flux_t.npy'), tf)
np.save(os.path.join(A, 'flux_low.npy'), flux_low)
with open(os.path.join(A, 'grid.json'), 'w', encoding='utf-8') as fp:
    json.dump(dict(beat0=beat0, period=period, bpm=bpm, duration=dur), fp, indent=1)

print(f"duration={dur:.2f}s  beat0={beat0:.4f}s  period={period:.4f}s  bpm={bpm:.2f}")
