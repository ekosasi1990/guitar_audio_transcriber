import music21


def notes_to_tab(notes, bpm, output_path):
    """Generate a guitar tablature MusicXML file using music21."""
    stream = music21.stream.Score()
    part = music21.stream.Part()
    guitar = music21.instrument.Guitar()
    part.insert(0, guitar)

    # Standard tuning
    tunings = [64, 59, 55, 50, 45, 40]  # E4 B3 G3 D3 A2 E2

    for n in sorted(notes, key=lambda x: x["start"]):
        midi = n["pitch"]
        duration = music21.duration.Duration(n["end"] - n["start"])
        string, fret = find_string_and_fret(midi, tunings)
        if string is None:
            continue
        tab_note = music21.note.Note(midi)
        tab_note.duration = duration
        tab_notation = music21.tablature.GuitarTabNote(midi, string + 1, fret)
        tab_note.articulations.append(tab_notation)
        part.insert(n["start"], tab_note)

    stream.insert(0, music21.tempo.MetronomeMark(referent="quarter", number=int(bpm)))
    stream.insert(0, part)
    stream.write("musicxml", fp=output_path)
    return output_path


def find_string_and_fret(midi, tunings):
    """Find the string (0-5) and fret for a given MIDI pitch."""
    for string, open_pitch in enumerate(tunings):
        if open_pitch <= midi <= open_pitch + 24:
            return string, midi - open_pitch
    return None, None
