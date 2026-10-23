import music21
from ..audio_processing.quantization import group_events
from .fingering import assign_fingering

GRID = 0.25  # sixteenth-note grid, in quarter lengths

# Quarter lengths a single rest/note can express (powers of two with up to
# two augmentation dots).
_EXPRESSIBLE = sorted(
    {
        base * mult
        for k in range(-4, 5)
        for base, mult in [(2.0**k, 1.0), (2.0**k, 1.5), (2.0**k, 1.75)]
    }
)


def notes_to_tab(notes, bpm, output_path, beats_per_measure=4, string_set="all"):
    """Generate a guitar tablature MusicXML file using music21."""
    stream = music21.stream.Score()
    part = music21.stream.Part()
    guitar = music21.instrument.Guitar()
    part.insert(0, guitar)
    part.insert(0, music21.meter.TimeSignature(f"{beats_per_measure}/4"))

    cursor = 0.0
    for group in group_events(notes):
        n = dict(group[0], end=max(note["end"] for note in group))
        positions = assign_fingering([note["pitch"] for note in group], string_set)
        if not positions:
            continue
        start_ql = round(n["start"] * bpm / 60 / GRID) * GRID
        duration_ql = max(
            GRID,
            n.get(
                "beat_duration", round((n["end"] - n["start"]) * bpm / 60 / GRID) * GRID
            ),
        )
        start_ql = max(start_ql, cursor)
        append_rests(part, start_ql - cursor)
        members = []
        for pitch in sorted(positions):
            member = music21.note.Note(pitch)
            string, fret = positions[pitch]
            member.articulations.append(music21.articulations.StringIndication(string))
            member.articulations.append(music21.articulations.FretIndication(fret))
            members.append(member)
        tab_note = music21.chord.Chord(members) if len(members) > 1 else members[0]
        tab_note.duration = expressible_duration(duration_ql)
        if (
            "beat_duration" in n
            and (n["end"] - n["start"]) * bpm / 60 < duration_ql * 0.85
        ):
            tab_note.articulations.append(music21.articulations.Staccato())
        part.append(tab_note)
        cursor = start_ql + duration_ql

    stream.insert(0, music21.tempo.MetronomeMark(referent="quarter", number=int(bpm)))
    stream.insert(0, part)
    stream.write("musicxml", fp=output_path)
    return output_path


def append_rests(part, quarter_length):
    """Fill a gap with rests, decomposed into notatable durations."""
    while quarter_length >= GRID - 1e-9:
        chunk = max(v for v in _EXPRESSIBLE if v <= quarter_length + 1e-9)
        part.append(music21.note.Rest(quarterLength=chunk))
        quarter_length -= chunk


def expressible_duration(quarter_length):
    """Snap a quarter-length to the nearest duration music21 can notate."""
    for candidate in (
        round(quarter_length * 4) / 4,
        round(quarter_length * 2) / 2,
        round(quarter_length),
    ):
        d = music21.duration.Duration(max(candidate, GRID))
        if d.type not in ("inexpressible", "complex", "zero"):
            return d
    return music21.duration.Duration(1.0)


def find_string_and_fret(midi, tunings):
    """Find the string (0-5) and fret for a given MIDI pitch."""
    for string, open_pitch in enumerate(tunings):
        if open_pitch <= midi <= open_pitch + 24:
            return string, midi - open_pitch
    return None, None
