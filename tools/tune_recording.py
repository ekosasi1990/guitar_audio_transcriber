"""Tuning harness for recorded takes.

Usage:
    .venv/Scripts/python tools/tune_recording.py recordings/take-XXX.wav
    .venv/Scripts/python tools/tune_recording.py recordings/take-XXX.wav expected.json

Prints every detected note (onset time, end, pitch, name, confidence) and
the detected onsets, so a recording can be compared against what was
actually played. An optional expected-events JSON file scores the result:
    [{"pitch": 40, "start": 0.5}, ...]  (pitch = MIDI number, start = seconds)
A detection matches when pitch is equal and onset is within 100 ms.
"""

import json
import sys
import warnings
import argparse

warnings.filterwarnings("ignore")

import librosa
import pretty_midi

sys.path.insert(0, ".")
from src.backend.audio_processing.loader import load_audio
from src.backend.audio_processing.tempo_estimation import estimate_tempo


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("audio_path")
    parser.add_argument("expected_path", nargs="?")
    parser.add_argument(
        "--chords", action="store_true", help="Use polyphonic transcription"
    )
    args = parser.parse_args()
    audio_path, expected_path = args.audio_path, args.expected_path

    y, sr = load_audio(audio_path)
    bpm, _ = estimate_tempo(y, sr)

    from src.backend.api import _run_transcription

    notes, engine = _run_transcription(
        {"audio_path": audio_path, "y": y, "sr": sr},
        mode="chords" if args.chords else "melody",
    )

    onset_times = librosa.onset.onset_detect(y=y, sr=sr, units="time")

    print(f"file: {audio_path}")
    print(f"duration: {len(y) / sr:.2f}s  bpm estimate: {bpm:.1f}  engine: {engine}")
    print(
        f"librosa onsets ({len(onset_times)}): "
        + " ".join(f"{t:.2f}" for t in onset_times)
    )
    print(f"notes ({len(notes)}):")
    print(f"  {'onset':>6} {'end':>6} {'pitch':>5} {'name':>5} {'conf':>5} {'dur':>5}")
    for n in notes:
        name = pretty_midi.note_number_to_name(n["pitch"])
        print(
            f"  {n['start']:6.2f} {n['end']:6.2f} {n['pitch']:5d} {name:>5} "
            f"{n['velocity'] / 127:5.2f} {n['end'] - n['start']:5.2f}"
        )

    if expected_path:
        with open(expected_path) as f:
            expected = json.load(f)
        matched, missed = 0, []
        remaining = list(notes)
        for e in expected:
            hit = next(
                (
                    i
                    for i, n in enumerate(remaining)
                    if n["pitch"] == e["pitch"] and abs(n["start"] - e["start"]) < 0.1
                ),
                None,
            )
            if hit is not None:
                remaining.pop(hit)
                matched += 1
            else:
                missed.append(e)
        extra = remaining
        print(
            f"expected {len(expected)} onsets: matched {matched}, "
            f"missed {len(missed)}, extra detections {len(extra)}"
        )
        for e in missed:
            print(f"  missed: {e}")
        for n in extra:
            print(
                f"  extra:  {pretty_midi.note_number_to_name(n['pitch'])} "
                f"@ {n['start']:.2f}s"
            )


if __name__ == "__main__":
    main()
