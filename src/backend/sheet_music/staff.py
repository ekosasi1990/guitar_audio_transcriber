import music21
from ..audio_processing.quantization import group_events


def notes_to_musicxml(tracks, bpm, output_path, beats_per_measure=4):
    """Export timed notes into real measures, including rests and accidentals."""
    score = music21.stream.Score()
    for name, notes in tracks.items():
        part = music21.stream.Part()
        part.partName = name
        part.insert(0, music21.meter.TimeSignature(f"{beats_per_measure}/4"))
        part.insert(0, music21.tempo.MetronomeMark(number=bpm))
        for group in group_events(notes):
            event = dict(group[0], end=max(n["end"] for n in group))
            note = (
                music21.chord.Chord([n["pitch"] for n in group])
                if len(group) > 1
                else music21.note.Note(event["pitch"])
            )
            length = event.get(
                "beat_duration",
                max(0.25, round((event["end"] - event["start"]) * bpm / 60 * 4) / 4),
            )
            note.duration = music21.duration.Duration(length)
            if (
                "beat_duration" in event
                and (event["end"] - event["start"]) * bpm / 60 < length * 0.85
            ):
                note.articulations.append(music21.articulations.Staccato())
            offset = round(event["start"] * bpm / 60 * 4) / 4
            part.insert(offset, note)
        score.insert(0, part)
    score.write("musicxml", fp=output_path)
    return output_path
