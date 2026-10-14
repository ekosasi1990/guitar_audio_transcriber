"""Conservative confirmation that a buffered take contains intentional guitar playing."""

import librosa
import numpy as np
from .quantization import group_events


def confirm_playing(y, sr, notes):
    qualified = []
    if len(y) < 1024:
        return {"playing_confirmed": False, "music_start": None, "qualified_attacks": 0}
    levels = librosa.feature.rms(y=y, frame_length=1024, hop_length=220)[0]
    reference = float(np.percentile(levels, 95))
    for group in group_events(notes):
        start = group[0]["start"]
        end = min(max(n["end"] for n in group), start + 0.65, len(y) / sr)
        if end - start < 0.07:
            continue
        body = y[int((start + 0.01) * sr) : int(end * sr)]
        if len(body) < 1024:
            continue
        spectrum = abs(librosa.stft(body, n_fft=1024, hop_length=220, center=False))
        rms = np.sqrt(
            np.mean(
                librosa.util.frame(body, frame_length=1024, hop_length=220) ** 2, axis=0
            )
        )
        active = rms > max(float(rms.max()) * 0.18, 0.0005)
        flatness = librosa.feature.spectral_flatness(S=spectrum)[0]
        if np.sum(active) * 220 / sr < 0.025 or np.mean(flatness[active]) > 0.12:
            continue
        # A stable fundamental excludes speech glides and broadband handling
        # sounds. Chord spectra instead need sustained harmonic concentration.
        if len(group) == 1:
            f0 = librosa.yin(
                body,
                sr=sr,
                fmin=75,
                fmax=1400,
                frame_length=1024,
                hop_length=220,
                center=False,
            )
            midi = np.rint(librosa.hz_to_midi(f0))
            if np.mean(np.abs(midi - group[0]["pitch"]) <= 1) < 0.8:
                continue
        else:
            frequencies = librosa.fft_frequencies(sr=sr, n_fft=1024)
            mask = np.zeros(len(frequencies), bool)
            for note in group:
                f = librosa.midi_to_hz(note["pitch"])
                for harmonic in range(1, 13):
                    mask |= abs(frequencies - f * harmonic) < max(
                        22, f * harmonic * 0.015
                    )
            power = spectrum**2
            if power[mask].sum() / max(power.sum(), 1e-12) < 0.7:
                continue
        pre = y[max(0, int((start - 0.15) * sr)) : int(start * sr)]
        before = np.sqrt(np.mean(pre**2)) if len(pre) else 0
        after = float(np.sqrt(np.mean(body**2)))
        if after < max(0.0008, before * 0.65, reference * 0.25):
            continue
        early = np.sqrt(np.mean(body[: int(0.1 * sr)] ** 2))
        late = np.sqrt(np.mean(body[-int(0.1 * sr) :] ** 2))
        qualified.append(
            dict(
                start=start,
                end=end,
                short=end - start < 0.16,
                held=end - start >= 0.4
                and after > before * 2.5
                and late < early * 0.85,
            )
        )
    repeated = any(
        0.055 <= b["start"] - a["start"] <= 2.0
        for a, b in zip(qualified, qualified[1:])
    )
    if repeated and all(n["short"] for n in qualified):
        repeated = len(qualified) >= 3
    confirmed = repeated or any(n["held"] for n in qualified)
    return {
        "playing_confirmed": bool(confirmed),
        "music_start": (
            min((n["start"] for n in qualified), default=None) if confirmed else None
        ),
        "qualified_attacks": len(qualified),
    }
