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

warnings.filterwarnings("ignore")

import librosa
import pretty_midi

sys.path.insert(0, ".")
from src.backend.audio_processing.loader import load_audio
from src.backend.audio_processing.tempo_estimation import estimate_tempo


def main():
    audio_path = sys.argv[1]
    expected_path = sys.argv[2] if len(sys.argv) > 2 else None

    y, sr = load_audio(audio_path)
    bpm, _ = estimate_tempo(y, sr)

    try:
        from src.backend.audio_processing.neural_transcription import (
            transcribe_neural,
        )
        notes = transcribe_neural(audio_path, y=y, sr=sr)
        engine = "basic-pitch"
    except Exception as exc:  # pragma: no cover - manual tool
        print(f"basic-pitch unavailable: {exc}")
        return

    onset_times = librosa.onset.onset_detect(y=y, sr=sr, units="time")

    print(f"file: {audio_path}")
    print(f"duration: {len(y) / sr:.2f}s  bpm estimate: {bpm:.1f}  engine: {engine}")
    print(f"librosa onsets ({len(onset_times)}): "
          + " ".join(f"{t:.2f}" for t in onset_times))
    print(f"notes ({len(notes)}):")
    print(f"  {'onset':>6} {'end':>6} {'pitch':>5} {'name':>5} {'conf':>5} {'dur':>5}")
    for n in notes:
        name = pretty_midi.note_number_to_name(n["pitch"])
        print(f"  {n['start']:6.2f} {n['end']:6.2f} {n['pitch']:5d} {name:>5} "
              f"{n['velocity'] / 127:5.2f} {n['end'] - n['start']:5.2f}")

    if expected_path:
        with open(expected_path) as f:
            expected = json.load(f)
        matched, missed = 0, []
        for e in expected:
            hit = any(n["pitch"] == e["pitch"] and
                      abs(n["start"] - e["start"]) < 0.1 for n in notes)
            matched += hit
            if not hit:
                missed.append(e)
        extra = [n for n in notes if not any(
            n["pitch"] == e["pitch"] and abs(n["start"] - e["start"]) < 0.1
            for e in expected)]
        print(f"expected {len(expected)} onsets: matched {matched}, "
              f"missed {len(missed)}, extra detections {len(extra)}")
        for e in missed:
            print(f"  missed: {e}")
        for n in extra:
            print(f"  extra:  {pretty_midi.note_number_to_name(n['pitch'])} "
                  f"@ {n['start']:.2f}s")


if __name__ == "__main__":
    main()
