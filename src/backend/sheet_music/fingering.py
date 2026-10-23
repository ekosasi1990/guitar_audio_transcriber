"""Choose playable string/fret positions for a note or simultaneous chord."""

from itertools import product
from ..audio_processing.quantization import group_events

TUNING = [64, 59, 55, 50, 45, 40]
STRING_SETS = {"all": (1, 2, 3, 4, 5, 6), "top": (1, 2, 3), "bottom": (4, 5, 6)}


def assign_fingering(pitches, string_set="all"):
    pitches = sorted(set(pitches))
    choices = [
        [
            (i + 1, p - open_pitch)
            for i, open_pitch in enumerate(TUNING)
            if i + 1 in STRING_SETS[string_set] and 0 <= p - open_pitch <= 24
        ]
        for p in pitches
    ]
    if not all(choices):
        return {}
    best, best_score = None, None
    for positions in product(*choices):
        if len({string for string, fret in positions}) != len(positions):
            continue
        frets = [fret for string, fret in positions]
        score = (
            (max(frets) - min(frets), -sum(s for s, f in positions), sum(frets))
            if len(pitches) > 1
            else (frets[0], -positions[0][0], 0)
        )
        if best_score is None or score < best_score:
            best, best_score = positions, score
    return dict(zip(pitches, best or []))


def tablature_events(notes, string_set="all"):
    return [
        {
            "start": min(n["start"] for n in group),
            "end": max(n["end"] for n in group),
            "positions": [
                {"pitch": pitch, "string": position[0], "fret": position[1]}
                for pitch, position in assign_fingering(
                    [n["pitch"] for n in group], string_set
                ).items()
            ],
        }
        for group in group_events(notes)
    ]
