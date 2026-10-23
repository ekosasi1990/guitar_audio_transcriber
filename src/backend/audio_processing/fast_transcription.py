"""Short analysis windows for closely spaced guitar attacks."""

import librosa
import numpy as np


def transcribe_separated_melody(y, sr, noise_floor=0.3):
    """Resolve short plucks with clear silent gaps without spanning two attacks.

    Continuous or overlapping phrases stay on the normal attack-led path.
    """
    if len(y) < 1024:
        return None
    hop = 64
    level = librosa.feature.rms(y=y, frame_length=256, hop_length=hop)[0]
    peak = float(level.max())
    if peak < 1e-6:
        return None
    active = level > peak * 0.08
    # Fill very brief valleys; a few quiet samples are not another pluck.
    quiet = np.flatnonzero(~active)
    for run in np.split(quiet, np.where(np.diff(quiet) > 1)[0] + 1):
        if (
            len(run)
            and len(run) * hop / sr < 0.008
            and run[0] > 0
            and run[-1] < len(active) - 1
        ):
            active[run] = True
    boundaries = np.diff(np.r_[False, active, False].astype(int))
    regions = list(
        zip(np.flatnonzero(boundaries == 1), np.flatnonzero(boundaries == -1))
    )
    regions = [(a, b) for a, b in regions if (b - a) * hop >= 1024]
    if not regions or any((b - a) * hop / sr > 0.3 for a, b in regions):
        return None
    notes, strengths = [], []
    for a, b in regions:
        start, end = a * hop / sr, min(len(y) / sr, b * hop / sr)
        segment = y[int(start * sr) : int(end * sr)]
        if len(segment) < 1024:
            continue
        envelope = librosa.feature.rms(
            y=segment, frame_length=1024, hop_length=128, center=False
        )[0]
        spectrum = abs(librosa.stft(segment, n_fft=1024, hop_length=128, center=False))
        frames = envelope > envelope.max() * 0.25
        if np.mean(librosa.feature.spectral_flatness(S=spectrum)[0][frames]) > 0.12:
            return None
        f0 = librosa.yin(
            segment,
            sr=sr,
            fmin=75,
            fmax=1400,
            frame_length=1024,
            hop_length=128,
            center=False,
        )
        midi = np.rint(librosa.hz_to_midi(f0[frames])).astype(int)
        pitch = int(np.bincount(np.clip(midi, 0, 127)).argmax())
        if not 40 <= pitch <= 88 or np.mean(abs(midi - pitch) <= 1) < 0.8:
            return None
        rms = float(np.sqrt(np.mean(segment**2)))
        strengths.append(rms)
        notes.append(
            dict(
                pitch=pitch,
                start=float(start),
                end=float(end),
                velocity=int(np.clip(90 * np.sqrt(rms / peak), 35, 110)),
            )
        )
    if not notes:
        return None
    # Relative cleanup remains the same setting used by the regular detector.
    threshold = float(np.percentile(strengths, 75)) * noise_floor
    return [n for n, strength in zip(notes, strengths) if strength >= threshold]


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
