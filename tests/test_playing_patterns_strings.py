import io
import numpy as np
import pytest
import soundfile as sf
import xml.etree.ElementTree as ET
from pathlib import Path
from tests.conftest import SR, synth_pluck
from src.backend.audio_processing.melody_transcription import transcribe_melody
from src.backend.audio_processing.chord_transcription import transcribe_chords
from src.backend.audio_processing.playing_confirmation import confirm_playing
from src.backend.audio_processing.tempo_estimation import (
    estimate_note_tempo,
    repeated_pattern,
)
from src.backend.audio_processing.quantization import auto_fit_rhythm, group_events
from src.backend.sheet_music.fingering import assign_fingering


def phrase(pitches, gap, duration=None):
    y = np.zeros(int((0.5 + len(pitches) * gap) * SR))
    for i, ps in enumerate(pitches):
        tone = sum(synth_pluck(p, duration or gap * 0.9, amplitude=0.2) for p in ps)
        at = int((0.3 + i * gap) * SR)
        y[at : at + len(tone)] += tone
    return y


@pytest.mark.parametrize("gap", [0.12, 0.16, 0.22])
@pytest.mark.parametrize("chords", [False, True])
def test_fast_attacks_remain_separate(gap, chords):
    expected = [[44, 49] if chords else [55 + (i // 4) % 3] for i in range(12)]
    y = phrase(expected, gap)
    notes = transcribe_chords(y, SR) if chords else transcribe_melody(y, SR)
    groups = group_events(notes)
    assert [[n["pitch"] for n in g] for g in groups] == expected
    assert all(
        g[0]["end"] <= following[0]["start"] + 1e-6
        for g, following in zip(groups, groups[1:])
    )
    assert confirm_playing(y, SR, notes)["playing_confirmed"]


@pytest.mark.parametrize("kind", ["noise", "click", "hum"])
def test_incidental_sounds_do_not_confirm_playing(kind):
    t = np.arange(SR * 2) / SR
    y = (
        np.random.default_rng(42).normal(0, 0.1, len(t))
        if kind == "noise"
        else 0.1 * np.sin(2 * np.pi * 196 * t)
    )
    if kind == "click":
        y[:] = 0
        y[SR // 2 : SR // 2 + 100] = 0.8
    # Include a claimed pitch to ensure the gate checks the audio itself.
    notes = [{"pitch": 55, "start": 0.2, "end": 1.5, "velocity": 80}]
    assert not confirm_playing(y, SR, notes)["playing_confirmed"]


def test_confirmation_keeps_first_pluck_after_noise():
    y = phrase([[55], [57], [55]], 0.5)
    y[: int(0.12 * SR)] = np.random.default_rng(1).normal(0, 0.02, int(0.12 * SR))
    notes = transcribe_melody(y, SR)
    result = confirm_playing(y, SR, notes)
    assert result["playing_confirmed"]
    assert result["music_start"] == pytest.approx(0.3, abs=0.06)


@pytest.mark.parametrize("bpm", [80, 150, 240])
def test_repeated_groups_fit_four_per_bar_at_any_tempo(bpm):
    pulse = 60 / bpm
    rng = np.random.default_rng(42)
    notes = [
        {
            "pitch": p,
            "start": 3 + i * pulse + rng.uniform(-0.03, 0.03) * pulse,
            "end": 3 + (i + 1.2) * pulse,
            "velocity": 80,
        }
        for i in range(32)
        for p in [40 + (i // 4) % 4, 45 + (i // 4) % 4]
    ]
    detected, pattern = estimate_note_tempo(notes, bpm / 2)
    assert pattern and detected == pytest.approx(bpm, rel=0.01)
    fitted = group_events(auto_fit_rhythm(notes, detected))
    assert len(fitted) == 32
    for i, g in enumerate(fitted):
        assert g[0]["start"] == pytest.approx(i * 60 / detected, abs=1e-6)
        assert g[0]["end"] <= (i + 1) * 60 / detected + 1e-6
        assert len({n["end"] for n in g}) == 1
    for n in notes[20:]:
        n["start"] += 5 * pulse
        n["end"] += 5 * pulse
    assert repeated_pattern(notes) is None


def test_string_fingering_uses_selected_strings():
    assert assign_fingering([55], "top") == {55: (3, 0)}
    assert assign_fingering([55], "bottom") == {55: (4, 5)}
    assert assign_fingering([44, 49], "top") == {}
    assert assign_fingering([44, 49], "bottom") == {44: (6, 4), 49: (5, 4)}
    assert assign_fingering([75], "bottom") == {}


def test_string_selection_survives_timing_and_export(client):
    wav = io.BytesIO()
    sf.write(wav, phrase([[55], [55], [55]], 0.5), SR, format="WAV")
    pid = client.post(
        "/upload", files={"file": ("strings.wav", wav.getvalue(), "audio/wav")}
    ).json()["project_id"]
    for selection, string, fret in [("top", 3, 0), ("bottom", 4, 5)]:
        data = client.post(
            f"/transcribe/{pid}?string_set={selection}&trim=true&tidy=true"
        ).json()
        assert len(data["tracks"]["Guitar"]) == 3
        assert all(
            e["positions"] == [{"pitch": 55, "string": string, "fret": fret}]
            for e in data["tablature"]
        )
        data = client.post(f"/tempo/{pid}", json={"bpm": 140}).json()
        assert all(e["positions"][0]["string"] == string for e in data["tablature"])
        result = client.get(f"/sheet/{pid}?format=tab").json()
        root = ET.parse(result["sheet_path"]).getroot()
        assert {int(n.text) for n in root.findall(".//technical/string")} == {string}
    assert client.post(f"/transcribe/{pid}?string_set=invalid").status_code == 422


def test_restricted_live_chords(client):
    wav = io.BytesIO()
    sf.write(wav, phrase([[44, 49]] * 4, 0.4), SR, format="WAV")
    data = client.post(
        "/live?mode=chords&string_set=bottom",
        files={"file": ("live.wav", wav.getvalue(), "audio/wav")},
    ).json()
    assert data["playing_confirmed"]
    assert len(group_events(data["notes"])) == 4
    assert all(
        p["string"] in [4, 5, 6] for e in data["tablature"] for p in e["positions"]
    )


def test_mitski_lead_in_does_not_start_take(client):
    from src.backend.audio_processing.loader import load_audio

    path = Path(__file__).resolve().parents[1] / "recordings/mitski.wav"
    if not path.exists():
        pytest.skip("Local recording missing")
    y, sr = load_audio(str(path))
    for stop, confirmed in [(3.5, False), (4.2, True)]:
        wav = io.BytesIO()
        sf.write(wav, y[: int(stop * sr)], sr, format="WAV")
        data = client.post(
            "/live?mode=chords",
            files={"file": ("live.wav", wav.getvalue(), "audio/wav")},
        ).json()
        assert data["playing_confirmed"] is confirmed
        if confirmed:
            assert data["music_start"] == pytest.approx(3.26, abs=0.05)
            assert all(n["start"] <= data["analysis_end"] for n in data["notes"])
        else:
            assert data["notes"] == []


def test_quiet_passage_does_not_rearm_recording_gate(client):
    wav = io.BytesIO()
    sf.write(wav, phrase([[55]], 0.5, duration=0.2), SR, format="WAV")
    files = {"file": ("live.wav", wav.getvalue(), "audio/wav")}
    waiting = client.post("/live", files=files).json()
    started = client.post("/live?playing_started=true", files=files).json()
    assert not waiting["playing_confirmed"] and waiting["notes"] == []
    assert [n["pitch"] for n in started["notes"]] == [55]


def test_detect_tempo_returns_recorded_tempo_after_speed_edit(client):
    wav = io.BytesIO()
    sf.write(wav, phrase([[55], [57], [55], [57]], 0.5), SR, format="WAV")
    pid = client.post(
        "/upload", files={"file": ("tempo.wav", wav.getvalue(), "audio/wav")}
    ).json()["project_id"]
    data = client.post(f"/transcribe/{pid}?trim=true&tidy=true").json()
    expected = data["detected_bpm"]
    client.post(f"/tempo/{pid}", json={"bpm": 180})
    assert client.get(f"/tempo/{pid}").json()["bpm"] == pytest.approx(expected)
