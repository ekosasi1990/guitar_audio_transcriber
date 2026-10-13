"""Accuracy benchmark — NOT a functional gate.

Measures how well the naive onset+piptrack pipeline recovers a known synthetic
melody. The threshold is intentionally loose; this test exists to track the
transcription quality trend and catch regressions, not to define correctness.
Run only these benchmarks with:  pytest -m accuracy
"""
import numpy as np
import pytest

from src.backend.audio_processing import detect_onsets, detect_pitches
from src.backend.audio_processing.loader import load_audio
from tests.conftest import MELODY_EVENTS

pytestmark = pytest.mark.accuracy

ONSET_TOLERANCE = 0.10  # seconds


def test_melody_recovery_rate(melody_wav, capsys):
    y, sr = load_audio(melody_wav)
    onsets, offsets = detect_onsets(y, sr)
    groups = detect_pitches(y, sr, onsets, offsets)

    detected_by_onset = []
    for start, _, pitches in MELODY_EVENTS:
        group = next(
            (g for g in groups if abs(g["start"] - start) < ONSET_TOLERANCE),
            None,
        )
        detected_by_onset.append(
            group is not None and set(pitches) <= set(group["pitches"])
        )

    recovered = sum(detected_by_onset)
    with capsys.disabled():
        print(
            f"\n[accuracy] recovered {recovered}/{len(MELODY_EVENTS)} synthetic "
            f"notes (tolerance={ONSET_TOLERANCE}s)"
        )
    # Loose regression bar: at least half of the clean synthetic notes.
    assert recovered >= max(1, len(MELODY_EVENTS) // 2)
