"""Short analysis windows for closely spaced guitar attacks."""

import librosa
import numpy as np


def fast_attacks(y, sr, noise_floor=0.3):
    if len(y) < 2048 or np.max(abs(y)) < 1e-7:
        return np.array([])
    hop = 128
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop, n_fft=1024)
    frames = librosa.onset.onset_detect(
        onset_envelope=env,
        sr=sr,
        hop_length=hop,
        pre_max=3,
        post_max=3,
        pre_avg=12,
        post_avg=12,
        delta=0.12,
        wait=4,
    )
    proposals = []
    for frame in frames:
        t = max(0, frame * hop / sr - 0.022)
        body = y[int((t + 0.012) * sr) : int((t + 0.07) * sr)]
        pre = y[max(0, int((t - 0.05) * sr)) : max(0, int((t - 0.015) * sr))]
        if not len(body):
            continue
        rms = float(np.sqrt(np.mean(body**2)))
        before = float(np.sqrt(np.mean(pre**2))) if len(pre) else 0
        if rms >= before * 0.5:
            proposals.append((t, rms, float(env[frame])))
    if not proposals:
        return np.array([])
    threshold = np.percentile([n[1] for n in proposals], 75) * noise_floor
    merged = []
    for n in proposals:
        if n[1] < threshold:
            continue
        if merged and n[0] - merged[-1][0] < 0.055:
            if n[2] > merged[-1][2]:
                merged[-1] = n
        else:
            merged.append(n)
    return np.array([n[0] for n in merged])


def use_fast_windows(attacks):
    if len(attacks) < 4:
        return False
    gaps = np.diff(attacks)
    return bool(np.median(gaps) < 0.27 and np.mean(gaps < 0.27) > 0.65)


def transcribe_fast_melody(y, sr, attacks):
    notes = []
    peak = max(np.max(abs(y)), 1e-8)
    for i, start in enumerate(attacks):
        limit = attacks[i + 1] if i + 1 < len(attacks) else len(y) / sr
        stop = min(start + 0.145, limit - 0.003)
        segment = y[int((start + 0.01) * sr) : int(stop * sr)]
        if len(segment) < 1024:
            continue
        f0 = librosa.yin(
            segment,
            sr=sr,
            fmin=75,
            fmax=1400,
            frame_length=1024,
            hop_length=128,
            center=False,
        )
        midi = np.rint(librosa.hz_to_midi(f0)).astype(int)
        pitch = int(np.bincount(np.clip(midi, 0, 127)).argmax())
        if not 40 <= pitch <= 88 or np.mean(abs(midi - pitch) <= 1) < 0.7:
            continue
        spectrum = abs(librosa.stft(segment, n_fft=1024, hop_length=128, center=False))
        if np.mean(librosa.feature.spectral_flatness(S=spectrum)) > 0.15:
            continue
        rms = float(np.sqrt(np.mean(segment**2)))
        end = limit
        # A short quiet stretch distinguishes staccato from the next attack.
        hop = 128
        envelope = librosa.feature.rms(
            y=y[int(start * sr) : int(limit * sr)], frame_length=512, hop_length=hop
        )[0]
        for j in range(int(0.05 * sr / hop), len(envelope) - 2):
            if np.all(envelope[j : j + 3] < rms * 0.2):
                end = start + j * hop / sr
                break
        notes.append(
            dict(
                pitch=pitch,
                start=float(start),
                end=float(max(start + 0.03, end)),
                velocity=int(np.clip(100 * np.sqrt(rms / peak), 35, 110)),
            )
        )
    return notes
