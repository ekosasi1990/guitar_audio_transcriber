import numpy as np


def chord_to_midi(chord_name):
    """Very simple mapping from chord name to a set of MIDI pitches."""
    base = {
        "C": 48,
        "C#": 49,
        "Db": 49,
        "D": 50,
        "D#": 51,
        "Eb": 51,
        "E": 52,
        "F": 53,
        "F#": 54,
        "Gb": 54,
        "G": 55,
        "G#": 56,
        "Ab": 56,
        "A": 57,
        "A#": 58,
        "Bb": 58,
        "B": 59,
    }
    if len(chord_name) > 1 and chord_name[1] in ("#", "b"):
        root, quality = chord_name[:2], chord_name[2:]
    else:
        root, quality = chord_name[:1], chord_name[1:]
    root_pitch = base.get(root, 48)
    if "maj7" in quality:
        intervals = [0, 4, 7, 11]
    elif "m" in quality:
        intervals = [0, 3, 7] + ([10] if "7" in quality else [])
    elif "7" in quality:
        intervals = [0, 4, 7, 10]
    else:
        intervals = [0, 4, 7]
    return [root_pitch + i for i in intervals]


def generate_accompaniment(chords, bpm, total_duration):
    """
    Generate simple drum, bass, and keyboard backing tracks.
    chords: list of (start_beat, chord_name) tuples.
    """
    spb = 60.0 / bpm
    notes = {"Drums": [], "Bass": [], "Keyboard": []}

    for start_beat, chord in chords:
        start = start_beat * spb
        end = start + spb
        chord_pitches = chord_to_midi(chord)
        bass_pitch = chord_pitches[0] - 24

        # Bass quarter note
        notes["Bass"].append(
            {"pitch": bass_pitch, "start": start, "end": end, "velocity": 90}
        )

        # Keyboard chord
        for p in chord_pitches:
            notes["Keyboard"].append(
                {"pitch": p, "start": start, "end": start + 4 * spb, "velocity": 70}
            )

        # Simple drum pattern
        for sub in range(4):
            notes["Drums"].append(
                {
                    "pitch": 36,
                    "start": start + sub * (spb / 4),
                    "end": start + sub * (spb / 4) + 0.05,
                    "velocity": 100 if sub == 0 else 60,
                }
            )
            if sub % 2 == 1:
                notes["Drums"].append(
                    {
                        "pitch": 42,
                        "start": start + sub * (spb / 4),
                        "end": start + sub * (spb / 4) + 0.05,
                        "velocity": 70,
                    }
                )

    return notes
