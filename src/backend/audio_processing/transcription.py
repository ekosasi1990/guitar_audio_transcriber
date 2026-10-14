"""Transcription engine selection and playable-string constraints."""

import logging
from .onset_analysis import detect_onsets
from .pitch_detection import detect_pitches
from .quantization import group_events
from ..sheet_music.fingering import assign_fingering


def transcribe_audio(project, mode="melody", noise_floor=0.3, string_set="all"):
    notes, engine = _detect_notes(project, mode, noise_floor, string_set)
    from ..sheet_music.fingering import TUNING, STRING_SETS

    strings = STRING_SETS[string_set]
    notes = [
        n for n in notes if any(0 <= n["pitch"] - TUNING[s - 1] <= 24 for s in strings)
    ]
    # Reject an impossible voicing rather than displaying a partial chord.
    notes = [
        n
        for group in group_events(notes)
        if assign_fingering([n["pitch"] for n in group], string_set)
        for n in group
    ]
    return notes, engine


def _detect_notes(project, mode="melody", noise_floor=0.3, string_set="all"):
    """Select an engine and return its detected notes."""
    if mode == "melody":
        from .melody_transcription import transcribe_melody

        return transcribe_melody(project["y"], project["sr"], noise_floor), "melody"
    if mode == "chords":
        from .chord_transcription import transcribe_chords

        return (
            transcribe_chords(project["y"], project["sr"], noise_floor, string_set),
            "guitar-chords",
        )
    try:
        from .neural_transcription import transcribe_neural

        return (
            transcribe_neural(project["audio_path"], y=project["y"], sr=project["sr"]),
            "basic-pitch",
        )
    except Exception as exc:
        logging.warning("Basic Pitch unavailable (%s); using DSP pipeline", exc)

    y, sr = project["y"], project["sr"]
    onsets, offsets = detect_onsets(y, sr)
    raw_notes = detect_pitches(y, sr, onsets, offsets)
    flat_notes = []
    for group in raw_notes:
        for pitch in group["pitches"]:
            flat_notes.append(
                {
                    "pitch": pitch,
                    "start": group["start"],
                    "end": group["end"],
                    "velocity": 80,
                }
            )
    return flat_notes, "dsp"
