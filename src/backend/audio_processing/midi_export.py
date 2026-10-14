import os
import pretty_midi


def export_midi(notes, bpm, instruments, output_path, accompaniment=None):
    """Export a list of tracks to a MIDI file."""
    pm = pretty_midi.PrettyMIDI(initial_tempo=bpm)

    def add_track(instrument_name, track_notes, program=0, is_drum=False):
        inst = pretty_midi.Instrument(
            program=program, name=instrument_name, is_drum=is_drum
        )
        for n in track_notes:
            note = pretty_midi.Note(
                velocity=n.get("velocity", 80),
                pitch=n["pitch"],
                start=n["start"],
                end=n["end"],
            )
            inst.notes.append(note)
        pm.instruments.append(inst)

    for name, track_notes in notes.items():
        program = instruments.get(name, 0)
        add_track(name, track_notes, program)

    if accompaniment:
        for name, track_notes in accompaniment.items():
            add_track(name, track_notes, is_drum="drum" in name.lower())

    os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
    pm.write(output_path)
    return output_path
