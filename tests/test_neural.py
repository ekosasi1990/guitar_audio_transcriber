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

