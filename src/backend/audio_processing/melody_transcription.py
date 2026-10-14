"""Attack-led transcription for picked, single-note guitar melodies.

Pitch tracking alone confuses ringing strings and harmonics with new notes.
Use spectral flux to propose attacks, require new harmonic energy, then use
YIN for the fundamental. Chords have their own, separate transcription mode.
"""

import librosa
import numpy as np
from scipy.ndimage import median_filter


def transcribe_melody(y, sr, noise_floor=0.3):
    from .fast_transcription import (
        fast_attacks,
        use_fast_windows,
        transcribe_fast_melody,
    )

    rapid_attacks = fast_attacks(y, sr, noise_floor)
    if use_fast_windows(rapid_attacks):
        return transcribe_fast_melody(y, sr, rapid_attacks)
    if len(y) < 2048 or np.max(np.abs(y)) < 1e-7:
        return []
    # Relative scaling makes the same rejection settings work on quiet takes.
    y = np.asarray(y, dtype=float)
    scale = np.percentile(np.abs(y), 99)
    if scale < 1e-7:
        return []
    y = y * (0.11 / scale)
    hop, n_fft = 220, 8192
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    frames = librosa.onset.onset_detect(
        onset_envelope=env,
        sr=sr,
        hop_length=hop,
        pre_max=3,
        post_max=3,
        pre_avg=15,
        post_avg=15,
        delta=0.12,
        wait=8,
    )
    spectrum = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=hop))
    pitches = np.arange(40, 89)
    bins = librosa.midi_to_hz(pitches)[:, None] * np.arange(1, 7) * n_fft / sr
    bins = bins.astype(int)
    candidates = []
    for frame in frames:
        start = max(0.0, frame * hop / sr - 0.03)
        at = int(start * sr / hop)
        after = spectrum[:, at + 4 : at + 13]
        before = spectrum[:, max(0, at - 10) : max(1, at - 3)]
        if not after.size:
            continue
        post, pre = after.mean(axis=1), before.mean(axis=1)
        novelty = np.maximum(post - pre, 0)
        novelty_ratio = float(novelty.sum() / (post.sum() + 1e-9))
        # Remove the local broadband floor so a click underneath an old
        # ringing pitch cannot borrow that string's harmonic structure.
        tonal_novelty = np.maximum(novelty - median_filter(novelty, size=9), 0)
        values = np.maximum.reduce(
            [
                novelty[np.clip(bins + shift, 0, len(novelty) - 1)]
                for shift in (-1, 0, 1)
            ]
        )
        # Log compression gives weak fundamentals and higher partials a vote,
        # instead of selecting the loudest harmonic as another note.
        scores = np.log1p(values / 2).sum(axis=1) + np.log1p(values[:, 0] / 2)
        segment = y[int((start + 0.015) * sr) : int((start + 0.145) * sr)]
        if len(segment) < 2048:
            continue
        contour = librosa.yin(
            segment,
            sr=sr,
            fmin=75,
            fmax=1400,
            frame_length=2048,
            hop_length=hop,
            center=False,
        )
        rounded = np.rint(librosa.hz_to_midi(contour)).astype(int)
        pitch = int(np.bincount(np.clip(rounded, 0, 127)).argmax())
        spectral_pitch = int(pitches[scores.argmax()])
        score = float(scores.max())
        # A strong new upper fundamental may be masked by an old low string.
        if score > 10 and spectral_pitch != pitch:
            index = pitch - 40
            if 0 <= index < len(pitches):
                odd = values[index, ::2].sum()
                total = values[index].sum()
                if odd < total * 0.15 or abs(spectral_pitch - pitch) not in (
                    12,
                    19,
                    24,
                    28,
                ):
                    pitch = spectral_pitch
        elif abs(spectral_pitch - pitch) > 1 and abs(spectral_pitch - pitch) not in (
            12,
            19,
            24,
            28,
        ):
            continue
        clean_values = np.maximum.reduce(
            [
                tonal_novelty[np.clip(bins + shift, 0, len(novelty) - 1)]
                for shift in (-1, 0, 1)
            ]
        )
        clean_scores = np.log1p(clean_values / 2).sum(axis=1) + np.log1p(
            clean_values[:, 0] / 2
        )
        clean_score = float(clean_scores[pitch - 40]) if 40 <= pitch <= 88 else 0
        candidates.append(
            dict(
                start=start,
                pitch=pitch,
                score=score,
                clean_score=clean_score,
                novelty=novelty_ratio,
                rms=float(np.sqrt(np.mean(segment**2))),
            )
        )
    if not candidates:
        return []
    threshold = np.percentile([n["score"] for n in candidates], 90) * noise_floor
    attacks = []
    for n in candidates:
        if (
            n["score"] < threshold
            or n["clean_score"] < 3.2 * noise_floor / 0.3
            or n["novelty"] < 0.15
            or not 40 <= n["pitch"] <= 88
        ):
            continue
        # A pluck can produce two nearby flux peaks; keep its stronger attack.
        if attacks and n["start"] - attacks[-1]["start"] < 0.14:
            if n["rms"] > attacks[-1]["rms"]:
                attacks[-1] = n
        else:
            attacks.append(n)
    rms = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0]
    peak = max((n["rms"] for n in attacks), default=1)
    notes = []
    for i, n in enumerate(attacks):
        limit = attacks[i + 1]["start"] if i + 1 < len(attacks) else len(y) / sr
        # End at sustained silence, or the next intentional attack. This keeps
        # staccato gaps while preventing residual strings from piling up.
        end = limit
        first = int((n["start"] + 0.12) * sr / hop)
        last = min(len(rms), int(limit * sr / hop))
        quiet = rms[first:last] < max(n["rms"] * 0.18, 0.002)
        for j in range(max(0, len(quiet) - 3)):
            if quiet[j : j + 4].all():
                end = (first + j) * hop / sr
                break
        notes.append(
            dict(
                pitch=n["pitch"],
                start=float(n["start"]),
                end=float(max(n["start"] + 0.06, end)),
                velocity=int(np.clip(90 * np.sqrt(n["rms"] / peak), 35, 110)),
            )
        )
    return notes
