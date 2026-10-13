"""Functional tests for the audio-processing pipeline units.

These use deterministic synthetic signals (pure sine tones with known pitch
and timing) — they verify the pipeline runs and produces structurally correct
output. They are NOT accuracy benchmarks; see test_accuracy.py for those.
"""
import numpy as np

from src.backend.audio_processing import (
    detect_onsets,
    detect_pitches,
    estimate_tempo,
    quantize_notes,
)
from src.backend.audio_processing.loader import load_audio
from src.backend.editor.accompaniment import chord_to_midi
from src.backend.sheet_music.tablature import find_string_and_fret
from tests.conftest import MELODY_EVENTS


def test_load_audio_wav(melody_wav):
    y, sr = load_audio(melody_wav)
    assert sr == 22050
    assert y.ndim == 1
    assert len(y) / sr > 2.0
    assert np.max(np.abs(y)) > 0.1


def test_detect_onsets_finds_note_attacks(melody_wav):
    y, sr = load_audio(melody_wav)
    onsets, offsets = detect_onsets(y, sr)
    assert len(onsets) >= len(MELODY_EVENTS)
    assert len(onsets) == len(offsets)
    # Every synthesized attack should have a detected onset within 100 ms.
    for start, _, _ in MELODY_EVENTS:
        assert np.any(np.abs(onsets - start) < 0.10), f"no onset near {start}s"


def test_detect_pitches_recovers_expected_notes(melody_wav):
    y, sr = load_audio(melody_wav)
    onsets, offsets = detect_onsets(y, sr)
    groups = detect_pitches(y, sr, onsets, offsets)
    assert groups, "no pitch groups detected"

    expected = sorted({p for _, _, pitches in MELODY_EVENTS for p in pitches})
    detected = sorted({p for g in groups for p in g["pitches"]})
    for midi in expected:
        assert midi in detected, f"expected pitch {midi} not detected"

    for g in groups:
        assert 0.0 <= g["start"] < g["end"]
        assert all(24 <= p <= 104 for p in g["pitches"])


def test_detect_pitches_polyphonic_chord(tmp_path):
    import soundfile as sf
    from tests.conftest import synth_note

    sr = 22050
    tone = synth_note(64, 0.5, sr) + synth_note(67, 0.5, sr)  # E4 + G4
    path = tmp_path / "dyad.wav"
    sf.write(str(path), np.clip(tone, -1, 1), sr)
    y, _ = load_audio(str(path))
    onsets, offsets = detect_onsets(y, sr)
    groups = detect_pitches(y, sr, onsets, offsets)
    detected = {p for g in groups for p in g["pitches"]}
    assert {64, 67} <= detected


def test_estimate_tempo_returns_positive_finite_bpm(melody_wav):
    y, sr = load_audio(melody_wav)
    bpm, beats = estimate_tempo(y, sr)
    assert np.isfinite(bpm) and bpm > 0
    assert isinstance(beats, list)


def test_estimate_tempo_falls_back_on_silence():
    bpm, _ = estimate_tempo(np.zeros(22050, dtype=np.float32), 22050)
    assert np.isfinite(bpm) and bpm > 0


def test_quantize_notes_snaps_to_grid():
    notes = [{"pitch": 60, "start": 0.11, "end": 0.24, "velocity": 80}]
    out = quantize_notes(notes, bpm=120.0)  # 16th-note grid = 0.125 s
    assert out[0]["start"] == 0.125
    assert out[0]["end"] == 0.25
    assert out[0]["pitch"] == 60
    assert out[0]["velocity"] == 80


def test_quantize_notes_partial_strength():
    notes = [{"pitch": 60, "start": 0.11, "end": 0.24, "velocity": 80}]
    out = quantize_notes(notes, bpm=120.0, strength=0.5)
    assert abs(out[0]["start"] - (0.11 + (0.125 - 0.11) * 0.5)) < 1e-6


def test_quantize_notes_zero_duration_gets_min_length():
    notes = [{"pitch": 60, "start": 0.10, "end": 0.10, "velocity": 80}]
    out = quantize_notes(notes, bpm=120.0)
    assert out[0]["end"] > out[0]["start"]


def test_chord_to_midi_qualities():
    assert chord_to_midi("C") == [48, 52, 55]
    assert chord_to_midi("Am") == [57, 60, 64]
    assert chord_to_midi("G7") == [55, 59, 62, 65]
    assert chord_to_midi("Cmaj7") == [48, 52, 55, 59]
    assert chord_to_midi("C#7")[0] == 49
    assert chord_to_midi("Bb")[0] == 58


def test_find_string_and_fret():
    tunings = [64, 59, 55, 50, 45, 40]
    assert find_string_and_fret(64, tunings) == (0, 0)   # open high E
    assert find_string_and_fret(40, tunings) == (5, 0)   # open low E
    assert find_string_and_fret(65, tunings) == (0, 1)   # F on high E
    assert find_string_and_fret(30, tunings) == (None, None)  # out of range
