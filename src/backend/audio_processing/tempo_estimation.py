import librosa
import numpy as np


def estimate_tempo(y, sr):
    """Estimate BPM and beat times using librosa's beat tracker."""
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    if not beat_times.size:
        beat_times = np.arange(0.0, len(y) / sr, 60.0 / 120.0)
    tempo = float(np.atleast_1d(tempo)[0])
    if not np.isfinite(tempo) or tempo <= 0:
        tempo = 120.0
    return tempo, beat_times.tolist()


def repeated_pattern(notes, beats_per_measure=4):
    """Recognize repeated chord blocks with regular attacks and no long rests."""
    from .quantization import group_events

    groups = group_events(notes)
    if len(groups) < beats_per_measure * 3:
        return None
    voicings = [tuple(sorted(n["pitch"] for n in group)) for group in groups]
    runs = []
    begin = 0
    for i in range(1, len(voicings) + 1):
        if i == len(voicings) or voicings[i] != voicings[begin]:
            runs.append((begin, i - begin))
            begin = i
    starts = np.array([group[0]["start"] for group in groups])
    intervals = np.diff(starts)
    period = float(np.median(intervals))
    if (
        period <= 0
        or np.median(abs(intervals - period)) / period > 0.18
        or max(intervals) / period > 1.8
    ):
        return None
    matching = [
        (start, length) for start, length in runs if length == beats_per_measure
    ]
    if len(matching) < 3 or sum(length for _, length in matching) / len(groups) < 0.65:
        return None
    if np.mean([start % beats_per_measure == 0 for start, length in matching]) < 0.85:
        return None
    # Fit a pulse across the entire phrase instead of accumulating local
    # timing errors. Pitch order and event count never change.
    slope = float(np.polyfit(np.arange(len(starts)), starts - starts[0], 1)[0])
    bpm = 60 / slope
    if not 20 <= bpm <= 300:
        return None
    return {
        "attacks_per_bar": beats_per_measure,
        "bpm": bpm,
        "confidence": len(matching) / len(runs),
    }


def estimate_note_tempo(notes, fallback=120, beats_per_measure=4):
    """Use reliable musical attacks; disambiguate pulse with repeated blocks."""
    from .quantization import group_events

    pattern = repeated_pattern(notes, beats_per_measure)
    if pattern:
        return pattern["bpm"], pattern
    groups = group_events(notes)
    if len(groups) < 4:
        return fallback, None
    intervals = np.diff([g[0]["start"] for g in groups])
    median = np.median(intervals)
    pulse = intervals[(intervals > median * 0.65) & (intervals < median * 1.5)]
    if len(pulse) < 3:
        return fallback, None
    base = 60 / float(np.median(pulse))
    candidates = [base * factor for factor in (0.5, 1, 2) if 20 <= base * factor <= 300]
    if not candidates:
        return fallback, None
    return min(candidates, key=lambda v: abs(np.log(v / fallback))), None
