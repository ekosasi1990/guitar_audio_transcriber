"""Functional test for the Basic Pitch transcription backend.

Skipped when basic-pitch is not installed (it is an optional dependency).
"""
import pytest

pytest.importorskip("basic_pitch")

from src.backend.audio_processing.neural_transcription import transcribe_neural
from tests.conftest import MELODY_EVENTS, PLUCK_EVENTS


def test_basic_pitch_recovers_melody(melody_wav):
    notes = transcribe_neural(melody_wav)
    assert notes, "basic-pitch returned no notes"
    detected = {n["pitch"] for n in notes}
    for _, _, pitches in MELODY_EVENTS:
        for midi in pitches:
            assert midi in detected, f"expected pitch {midi} not detected"
    for n in notes:
        assert 0 <= n["start"] < n["end"]
        assert 1 <= n["velocity"] <= 127


def test_sustain_tail_does_not_retrigger(plucks_wav):
    """A plucked string keeps ringing ('humming'); that sustain must not
    spawn extra notes (commonly octave/harmonic artifacts)."""
    notes = transcribe_neural(plucks_wav)
    detected = {n["pitch"] for n in notes}
    expected = {p for _, _, pitches in PLUCK_EVENTS for p in pitches}
    assert expected <= detected
    # No spurious pitches — especially no octave artifacts from the tail.
    assert detected <= expected


def test_repluck_while_ringing_is_two_onsets(replucks_wav):
    """Re-plucking a still-ringing string is a new onset, not sustain:
    two separate note events, not one fused note."""
    notes = transcribe_neural(replucks_wav)
    at_64 = sorted((n for n in notes if n["pitch"] == 64),
                   key=lambda n: n["start"])
    assert len(at_64) >= 2
    assert abs(at_64[0]["start"] - 0.10) < 0.15
    assert abs(at_64[1]["start"] - 0.80) < 0.15
    # The second attack's start is the first attack's end.
    assert abs(at_64[0]["end"] - at_64[1]["start"]) < 0.15

