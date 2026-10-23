"""Unrelated pitches and altered audio guard against recording-specific rules."""

from pathlib import Path

import librosa
import numpy as np
import pytest

from src.backend.audio_processing.loader import load_audio
from src.backend.audio_processing.melody_transcription import transcribe_melody
from tests.conftest import SR, synth_pluck
from tests.test_melody import EXPECTED


@pytest.mark.parametrize("seed", [3, 17, 91])
@pytest.mark.parametrize("gap", [0.16, 0.25, 0.4, 0.7])
def test_unrelated_melodies_with_uneven_timing_and_loudness(seed, gap):
    rng = np.random.default_rng(seed)
    pitches = rng.integers(40, 77, 12).tolist()
    pitches[3], pitches[8] = pitches[2], pitches[7]
    starts = (
        0.3 + np.arange(len(pitches)) * gap + rng.uniform(-0.012, 0.012, len(pitches))
    )
    duration = gap * 0.65
    y = rng.normal(0, 0.0002, int((starts[-1] + duration + 0.3) * SR))
    for start, pitch in zip(starts, pitches):
        tone = synth_pluck(pitch, duration, amplitude=rng.uniform(0.12, 0.25))
        at = int(start * SR)
        y[at : at + len(tone)] += tone
    notes = transcribe_melody(y, SR)
    assert [n["pitch"] for n in notes] == pitches
    assert [n["start"] for n in notes] == pytest.approx(starts, abs=0.05)


@pytest.mark.parametrize("take", ["smooth", "take-20261014-124828-940576"])
@pytest.mark.parametrize("semitones", [-2, 2])
def test_changed_key_and_speed_without_song_settings(take, semitones):
    path = Path(__file__).resolve().parents[1] / "recordings" / f"{take}.wav"
    if not path.exists():
        pytest.skip("Local reference recording missing")
    y, sr = load_audio(str(path))
    shifted = librosa.resample(y, orig_sr=sr * 2 ** (semitones / 12), target_sr=sr)
    notes = transcribe_melody(shifted, sr)
    assert [n["pitch"] for n in notes] == [p + semitones for p in EXPECTED]
