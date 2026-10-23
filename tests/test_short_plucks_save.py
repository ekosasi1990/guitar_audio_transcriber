import io
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from tests.conftest import SR, synth_pluck
from src.backend.audio_processing.melody_transcription import transcribe_melody


@pytest.mark.parametrize("gap", [0.08, 0.10, 0.12, 0.16, 0.20])
@pytest.mark.parametrize("pitches", [(45, 45), (55, 55), (45, 55)])
def test_two_short_plucks_are_two_events(gap, pitches):
    y = np.zeros(SR * 2)
    for i, pitch in enumerate(pitches):
        tone = synth_pluck(pitch, 0.06, amplitude=0.2 if i == 0 else 0.12)
        at = int((0.3 + i * gap) * SR)
        y[at : at + len(tone)] += tone
    notes = transcribe_melody(y, SR)
    assert [n["pitch"] for n in notes] == list(pitches)
    assert [n["start"] for n in notes] == pytest.approx([0.3, 0.3 + gap], abs=0.02)
    assert notes[0]["end"] < notes[1]["start"]


def test_one_short_pluck_does_not_become_two():
    y = np.zeros(SR * 2)
    tone = synth_pluck(55, 0.06, amplitude=0.2)
    y[int(0.3 * SR) : int(0.3 * SR) + len(tone)] = tone
    notes = transcribe_melody(y, SR)
    assert [n["pitch"] for n in notes] == [55]


def test_long_sustained_note_with_quiet_click_is_not_split():
    y = np.zeros(SR * 2)
    tone = synth_pluck(55, 0.9, amplitude=0.3)
    y[int(0.3 * SR) : int(0.3 * SR) + len(tone)] = tone
    y[int(0.75 * SR) : int(0.75 * SR) + 120] += np.random.default_rng(3).normal(
        0, 0.003, 120
    )
    assert [n["pitch"] for n in transcribe_melody(y, SR)] == [55]


def test_save_uses_project_folder_and_keeps_original_bytes(
    client, tmp_path, monkeypatch
):
    from src.backend import api

    assert (
        Path(api.RECORDINGS_DIR).resolve()
        == Path(__file__).resolve().parents[1] / "recordings"
    )
    monkeypatch.setattr(api, "RECORDINGS_DIR", str(tmp_path / "recordings"))
    wav = io.BytesIO()
    sf.write(wav, synth_pluck(55, 0.2), SR, format="WAV")
    paths = []
    for _ in range(2):
        response = client.post(
            "/recordings",
            files={"file": ("source.wav", wav.getvalue(), "audio/wav")},
            data={"name": "take"},
        )
        assert response.status_code == 200
        path = Path(response.json()["path"])
        paths.append(path)
        assert path.parent == tmp_path / "recordings"
        assert path.read_bytes() == wav.getvalue()
    assert paths[0] != paths[1]


def test_two_short_notes_confirm_live_recording(client):
    y = np.zeros(SR * 2)
    for start in [0.3, 0.42]:
        tone = synth_pluck(55, 0.06, amplitude=0.2)
        at = int(start * SR)
        y[at : at + len(tone)] = tone
    wav = io.BytesIO()
    sf.write(wav, y, SR, format="WAV")
    response = client.post(
        "/live", files={"file": ("take.wav", wav.getvalue(), "audio/wav")}
    )
    assert response.status_code == 200
    result = response.json()
    assert result["playing_confirmed"]
    assert len(result["notes"]) == 2
