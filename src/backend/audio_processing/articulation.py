"""Onset vs. sustain separation for transcribed notes.

A note event has two distinct parts: the onset (the string was plucked or
strummed) and the sustain (the string keeps vibrating). Neural models tend
to fuse a re-plucked note into one long event when the ringing tail of the
previous instance is still sounding. This module detects real attacks with
librosa's onset detector and splits a held note only when the note's own
frequency band gains energy at the onset — evidence of a re-articulation,
not just another note in the chord.
"""
import numpy as np
import librosa
from scipy.signal import butter, sosfiltfilt


def _midi_hz(midi):
    return 440.0 * 2.0 ** ((midi - 69) / 12.0)


def _band_rms(y, sr, f_lo, f_hi, t0, t1):
    i0, i1 = max(0, int(t0 * sr)), min(len(y), int(t1 * sr))
    if i1 - i0 < 64:
        return 0.0
    sos = butter(4, [f_lo / (sr / 2), min(f_hi / (sr / 2), 0.99)],
                 btype="band", output="sos")
    return float(np.sqrt(np.mean(sosfiltfilt(sos, y[i0:i1]) ** 2)))


def _join_sustains(notes, onset_times, seam_tol=0.05, max_gap=0.03):
    """Merge abutting same-pitch events that have NO onset at the seam —
    the model split one sustained note internally. A seam with a real
    onset is a re-attack and stays split.
    """
    out = []
    for n in sorted(notes, key=lambda n: (n["start"], n["pitch"])):
        prev = out[-1] if out else None
        if prev and prev["pitch"] == n["pitch"]:
            seam = n["start"]
            gap = seam - prev["end"]
            has_onset = any(abs(t - seam) <= seam_tol for t in onset_times)
            if gap <= max_gap and not has_onset:
                prev["end"] = max(prev["end"], n["end"])
                prev["velocity"] = max(prev["velocity"], n["velocity"])
                continue
        out.append(dict(n))
    return out


def split_rearticulated(notes, y, sr, window=0.05, growth=1.2,
                        min_segment=0.08):
    """Separate attacks from sustain.

    1. Same-pitch events split internally by the model are re-joined when
       no onset exists at the seam (sustain, not a new attack).
    2. Notes spanning a real onset are split at it only when the note's
       own frequency band gains energy there — evidence of a re-pluck.
       Onsets belonging to other pitches (e.g. the next note of a
       strummed chord) leave the sustained note alone.
    """
    if not notes:
        return notes
    onset_times = librosa.onset.onset_detect(
        y=y, sr=sr, units="time", backtrack=True
    )
    out = []
    for note in _join_sustains(notes, onset_times):
        f = _midi_hz(note["pitch"])
        f_lo, f_hi = f * 0.94, f * 1.06
        cur_start = note["start"]
        for t in onset_times:
            if not (cur_start + min_segment < t < note["end"] - min_segment):
                continue
            before = _band_rms(y, sr, f_lo, f_hi, t - window, t)
            after = _band_rms(y, sr, f_lo, f_hi, t, t + window)
            if after > growth * before and after > 0.002:
                out.append({**note, "start": cur_start, "end": float(t)})
                cur_start = float(t)
        out.append({**note, "start": cur_start, "end": note["end"]})
    out.sort(key=lambda n: (n["start"], n["pitch"]))
    return out
