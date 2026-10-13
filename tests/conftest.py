import os
import sys

import numpy as np
import pytest
import soundfile as sf

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(REPO_ROOT, "src")
for p in (REPO_ROOT, SRC):
    if p not in sys.path:
        sys.path.insert(0, p)

SR = 22050


def midi_to_hz(midi):
    return 440.0 * 2 ** ((midi - 69) / 12)


def synth_note(midi, duration, sr=SR, amplitude=0.6):
    """One note: pure sine with a fast attack and exponential decay so that
    onset detection sees a clear attack transient."""
    n = int(duration * sr)
    t = np.arange(n) / sr
    env = np.minimum(t / 0.005, 1.0) * np.exp(-15.0 * t)
    return amplitude * np.sin(2 * np.pi * midi_to_hz(midi) * t) * env


def synth_wav(path, events, sr=SR):
    """Write a deterministic WAV.

    events: list of (start_time_seconds, duration_seconds, [midi_pitches]).
    Pitches are summed to allow simple chords. Silent gaps separate notes.
    """
    total = max(start + dur for start, dur, _ in events) + 0.25
    y = np.zeros(int(total * sr), dtype=np.float32)
    for start, dur, pitches in events:
        tone = np.zeros(int(dur * sr), dtype=np.float32)
        for midi in pitches:
            tone += synth_note(midi, dur, sr)
        tone = np.clip(tone, -1.0, 1.0)
        i0 = int(start * sr)
        y[i0 : i0 + len(tone)] += tone
    sf.write(str(path), y, sr)
    return y, sr


def synth_pluck(midi, duration, sr=SR, amplitude=0.5):
    """A more guitar-like note: harmonics plus a long decaying sustain tail."""
    n = int(duration * sr)
    t = np.arange(n) / sr
    env = np.minimum(t / 0.004, 1.0) * (0.25 + 0.75 * np.exp(-1.8 * t))
    sig = np.zeros(n)
    for harmonic, amp in ((1, 1.0), (2, 0.45), (3, 0.25), (4, 0.12)):
        sig += amp * np.sin(2 * np.pi * midi_to_hz(midi) * harmonic * t)
    return amplitude * sig * env


# Plucked notes with sustain tails — exercises re-articulation filtering.
PLUCK_EVENTS = [(0.10, 1.40, [64]), (1.90, 1.40, [67]), (3.70, 1.40, [76])]


@pytest.fixture(scope="session")
def plucks_wav(tmp_path_factory):
    """WAV of guitar-like plucks written with the sustain envelope."""
    path = tmp_path_factory.mktemp("audio") / "plucks.wav"
    sr = SR
    total = max(s + d for s, d, _ in PLUCK_EVENTS) + 0.25
    y = np.zeros(int(total * sr), dtype=np.float32)
    for start, dur, pitches in PLUCK_EVENTS:
        tone = np.zeros(int(dur * sr), dtype=np.float32)
        for midi in pitches:
            tone += synth_pluck(midi, dur, sr)
        tone = np.clip(tone, -1.0, 1.0)
        i0 = int(start * sr)
        y[i0 : i0 + len(tone)] += tone
    sf.write(str(path), y, sr)
    return str(path)


# A simple "melody": G4, B4, D5, G4 with true silence between notes.
MELODY_EVENTS = [
    (0.10, 0.40, [67]),  # G4
    (0.70, 0.40, [71]),  # B4
    (1.30, 0.40, [74]),  # D5
    (1.90, 0.50, [67]),  # G4
]


@pytest.fixture(scope="session")
def melody_wav(tmp_path_factory):
    path = tmp_path_factory.mktemp("audio") / "melody.wav"
    synth_wav(path, MELODY_EVENTS)
    return str(path)


@pytest.fixture()
def client():
    from fastapi.testclient import TestClient
    from src.backend.api import app

    return TestClient(app)
