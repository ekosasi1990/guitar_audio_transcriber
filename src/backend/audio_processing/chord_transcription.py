"""Attack-aligned guitar chords, with harmonic suppression and local voicing consensus."""

from collections import Counter
import librosa
import numpy as np
from scipy.ndimage import median_filter


def transcribe_chords(y, sr, noise_floor=0.3, string_set="all"):
    if len(y) < 4096 or np.max(np.abs(y)) < 1e-7:
        return []
    hop, n_fft = 220, 16384
    env = librosa.onset.onset_strength(y=y, sr=sr, hop_length=hop)
    from .fast_transcription import fast_attacks, use_fast_windows

    rapid_attacks = fast_attacks(y, sr, noise_floor)
    fast = use_fast_windows(rapid_attacks)
    if fast:
        attack_times = rapid_attacks
    else:
        frames = librosa.onset.onset_detect(
            onset_envelope=env,
            sr=sr,
            hop_length=hop,
            pre_max=3,
            post_max=3,
            pre_avg=15,
            post_avg=15,
            delta=0.1,
            wait=12,
        )
        attack_times = np.maximum(0, frames * hop / sr - 0.03)
    frequencies = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    pitches = np.arange(40, 89)
    from ..sheet_music.fingering import TUNING, STRING_SETS

    strings = STRING_SETS[string_set]
    playable = np.array(
        [any(0 <= p - TUNING[s - 1] <= 24 for s in strings) for p in pitches]
    )
    masks = [
        [
            np.where((frequencies > f * k * 0.989) & (frequencies < f * k * 1.011))[0]
            for k in range(1, 9)
        ]
        for f in librosa.midi_to_hz(pitches)
    ]

    def partials(spectrum):
        return np.array(
            [[np.max(spectrum[ix], initial=0) for ix in pitch] for pitch in masks]
        )

    candidates = []
    for attack_index, start in enumerate(attack_times):
        frame = min(len(env) - 1, max(0, round((start + 0.03) * sr / hop)))
        body_start = start + 0.01 if fast else start + 0.03
        stop = (
            min(start + 0.26, attack_times[attack_index + 1] - 0.003)
            if fast and attack_index + 1 < len(attack_times)
            else start + 0.26
        )
        segment = y[int(body_start * sr) : int(stop * sr)]
        if len(segment) < 1024:
            continue
        rms = float(np.sqrt(np.mean(segment**2)))
        spectrum = np.abs(np.fft.rfft(segment * np.hanning(len(segment)), n=n_fft))
        clean = np.maximum(spectrum - median_filter(spectrum, size=21), 0)
        clean /= max(clean.max(), 1e-8)
        original = partials(clean)
        valid = ((original[:, ::2] > 0.025).sum(axis=1) >= 2) & playable
        selected, scores = [], []
        for _ in range(len(strings)):
            values = partials(clean)
            score = np.log1p(values * 30).sum(axis=1)
            score[~valid] = 0
            for previous in selected:
                score[np.abs(pitches - previous) < 2] = 0
            index = int(score.argmax())
            threshold = (
                7
                if not selected
                else max(4.5, scores[0] * 0.45) if len(selected) >= 2 else 4.5
            )
            if score[index] < threshold:
                break
            pitch = int(pitches[index])
            selected.append(pitch)
            scores.append(float(score[index]))
            f = librosa.midi_to_hz(pitch)
            for k in range(1, 35):
                width = max(f * k * 0.012, sr / len(segment)) if fast else f * k * 0.012
                clean[abs(frequencies - f * k) < width] = 0
        if selected:
            candidates.append(
                dict(
                    start=start,
                    pitches=tuple(sorted(selected)),
                    root=selected[0],
                    rms=rms,
                    flux=float(env[frame]),
                    confidence=scores[-1] / scores[0],
                )
            )
    if not candidates:
        return []
    loudness = np.median([n["rms"] for n in candidates])
    flux = np.median([n["flux"] for n in candidates])
    candidates = [n for n in candidates if n["rms"] > loudness * noise_floor]
    if not candidates:
        return []
    intervals = np.diff([n["start"] for n in candidates])
    minimum_gap = (
        min(
            0.22,
            max(
                0.04 if fast else 0.1,
                np.median(intervals) * 0.55 if fast else np.median(intervals) * 0.7,
            ),
        )
        if len(intervals)
        else 0.12
    )
    attacks = []
    for n in candidates:
        if attacks and n["start"] - attacks[-1]["start"] < minimum_gap:
            if n["flux"] > attacks[-1]["flux"]:
                attacks[-1] = n
        else:
            attacks.append(n)
    attacks = [
        n
        for i, n in enumerate(attacks)
        if fast
        or n["flux"] > flux * 0.5
        or i == 0
        or n["root"] != attacks[i - 1]["root"]
    ]
    # Repeated voicings provide evidence for quiet strings obscured by louder
    # partials. No song-specific notes or chord sequence are supplied here.
    vocabulary = Counter(
        (n["root"], n["pitches"]) for n in attacks if len(n["pitches"]) > 1
    )
    consensus = {}
    for (root, chord), count in vocabulary.items():
        if count >= 2 and (root not in consensus or count > consensus[root][0]):
            consensus[root] = (count, chord)
    notes = []
    peak = max(n["rms"] for n in attacks)
    rms_envelope = librosa.feature.rms(y=y, frame_length=1024, hop_length=hop)[0]
    for i, n in enumerate(attacks):
        chord = n["pitches"]
        if (
            n["root"] in consensus
            and vocabulary[(n["root"], chord)] < 2
            and (len(chord) == 1 or (len(chord) == 2 and n["confidence"] < 0.5))
        ):
            chord = consensus[n["root"]][1]
        end = attacks[i + 1]["start"] if i + 1 < len(attacks) else len(y) / sr
        first, last = int((n["start"] + 0.12) * sr / hop), min(
            len(rms_envelope), int(end * sr / hop)
        )
        quiet = rms_envelope[first:last] < max(n["rms"] * 0.2, 1e-5)
        for j in range(max(0, len(quiet) - 3)):
            if quiet[j : j + 4].all():
                end = (first + j) * hop / sr
                break
        velocity = int(np.clip(90 * np.sqrt(n["rms"] / peak), 35, 110))
        for pitch in chord:
            notes.append(
                dict(
                    pitch=pitch,
                    start=float(n["start"]),
                    end=float(max(n["start"] + 0.06, end)),
                    velocity=velocity,
                )
            )
    return sorted(notes, key=lambda n: (n["start"], n["pitch"]))
