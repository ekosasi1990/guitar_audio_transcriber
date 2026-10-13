import music21

GRID = 0.25  # sixteenth-note grid, in quarter lengths

# Quarter lengths a single rest/note can express (powers of two with up to
# two augmentation dots).
_EXPRESSIBLE = sorted({
    base * mult
    for k in range(-4, 5)
    for base, mult in [(2.0 ** k, 1.0), (2.0 ** k, 1.5), (2.0 ** k, 1.75)]
})


def notes_to_tab(notes, bpm, output_path):
    """Generate a guitar tablature MusicXML file using music21."""
    stream = music21.stream.Score()
    part = music21.stream.Part()
    guitar = music21.instrument.Guitar()
    part.insert(0, guitar)

    # Standard tuning
    tunings = [64, 59, 55, 50, 45, 40]  # E4 B3 G3 D3 A2 E2

    cursor = 0.0
    for n in sorted(notes, key=lambda x: x["start"]):
        midi = n["pitch"]
        string, fret = find_string_and_fret(midi, tunings)
        if string is None:
            continue

        start_ql = round(n["start"] * bpm / 60.0 / GRID) * GRID
        duration_ql = round((n["end"] - n["start"]) * bpm / 60.0 / GRID) * GRID
        duration_ql = max(duration_ql, GRID)
        if start_ql < cursor:
            start_ql = cursor  # overlapping notes are flattened to sequential

        append_rests(part, start_ql - cursor)
        tab_note = music21.note.Note(midi)
        tab_note.duration = expressible_duration(duration_ql)
        tab_note.articulations.append(music21.articulations.StringIndication(string + 1))
        tab_note.articulations.append(music21.articulations.FretIndication(fret))
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
    for candidate in (round(quarter_length * 4) / 4,
                      round(quarter_length * 2) / 2,
                      round(quarter_length)):
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
