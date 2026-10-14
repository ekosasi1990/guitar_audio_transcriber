"""Regression coverage for real takes and attack-led melody transcription."""

from pathlib import Path

import numpy as np
import pytest

from src.backend.audio_processing.loader import load_audio
from src.backend.audio_processing.melody_transcription import transcribe_melody
from tests.conftest import MELODY_EVENTS, synth_pluck, SR

EXPECTED = sum(([bass, bass, 55, 55, 54, 54, 55, 55] for bass in (43, 45, 48, 57)), [])


@pytest.mark.parametrize("take", ["smooth", "rough"])
@pytest.mark.parametrize("gain", [1.0, 0.1])
def test_recorded_sequence(take, gain):
    path = Path(__file__).resolve().parents[1] / "recordings" / f"{take}.wav"
    if not path.exists():
        pytest.skip("Local reference recordings are not included in the repository")
    y, sr = load_audio(str(path))
    notes = transcribe_melody(y * gain, sr)
    assert [n["pitch"] for n in notes] == EXPECTED
    assert all(n["end"] > n["start"] for n in notes)
    assert all(a["end"] <= b["start"] for a, b in zip(notes, notes[1:]))
    if take == "smooth":
        assert sum(b["start"] - a["end"] > 0.08 for a, b in zip(notes, notes[1:])) >= 16


def test_clean_melody(melody_wav):
    y, sr = load_audio(melody_wav)
    notes = transcribe_melody(y, sr)
    assert [n["pitch"] for n in notes] == [p[0] for _, _, p in MELODY_EVENTS]
    assert all(abs(n["start"] - e[0]) < 0.1 for n, e in zip(notes, MELODY_EVENTS))


def test_repeated_plucks(replucks_wav):
    y, sr = load_audio(replucks_wav)
    notes = transcribe_melody(y, sr)
    assert [n["pitch"] for n in notes] == [64, 64]
    assert abs(notes[1]["start"] - 0.8) < 0.1


def test_silence():
    assert transcribe_melody(np.zeros(22050), 22050) == []


def test_quiet_clicks_under_sustained_notes_are_rejected():
    rng = np.random.default_rng(12)
    y = np.zeros(SR * 4)
    events = [(0.4, 43), (1.2, 43), (2.0, 55), (2.8, 54)]
    for start, pitch in events:
        tone = synth_pluck(pitch, 0.65, amplitude=0.3)
        at = int(start * SR)
        y[at : at + len(tone)] += tone
    for start in (0.15, 0.95, 1.75, 3.6):
        at = int(start * SR)
        y[at : at + 440] += rng.normal(0, 0.012, 440)
    notes = transcribe_melody(y, SR)
    assert [n["pitch"] for n in notes] == [p for _, p in events]
    assert all(abs(n["start"] - e[0]) < 0.1 for n, e in zip(notes, events))


def test_default_api_and_playback(client):
    path = Path(__file__).resolve().parents[1] / "recordings" / "rough.wav"
    if not path.exists():
        pytest.skip("Local reference recording missing")
    with path.open("rb") as recording:
        result = client.post(
            "/upload", files={"file": (path.name, recording, "audio/wav")}
        )
    pid = result.json()["project_id"]
    result = client.post(f"/transcribe/{pid}")
    assert result.status_code == 200
    assert result.json()["engine"] == "melody"
    assert [n["pitch"] for n in result.json()["tracks"]["Guitar"]] == EXPECTED
    assert client.post(f"/transcribe/{pid}?mode=invalid").status_code == 422
    result = client.post(f"/playback/{pid}")
    assert result.status_code == 200
    assert result.content[:4] == b"RIFF"
    result = client.get(f"/sheet/{pid}?download=true")
    assert result.status_code == 200
    assert "attachment" in result.headers["content-disposition"]
