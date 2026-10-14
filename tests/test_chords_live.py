import io
from pathlib import Path
import numpy as np
import pytest
import soundfile as sf
import xml.etree.ElementTree as ET

from src.backend.audio_processing.loader import load_audio
from src.backend.audio_processing.chord_transcription import transcribe_chords
from src.backend.audio_processing.quantization import (
    auto_fit_rhythm,
    fit_rhythm,
    group_events,
)
from src.backend.sheet_music.fingering import assign_fingering
from tests.conftest import synth_pluck, SR

ROOT = Path(__file__).resolve().parents[1]
FRETS = (
    ([4] * 4 + [0] * 4 + [9] * 4 + [7] * 4) * 3
    + [0] * 4
    + [4] * 2
    + [5] * 2
    + [7] * 4
    + [0] * 4
)
EXPECTED = [[40 + fret, 45 + fret] for fret in FRETS]


@pytest.mark.parametrize("gain", [1.0, 0.1])
def test_mitski_64_chord_attacks(gain):
    path = ROOT / "recordings/mitski.wav"
    if not path.exists():
        pytest.skip("Local recording missing")
    y, sr = load_audio(str(path))
    notes = transcribe_chords(y * gain, sr)
    groups = group_events(notes)
    assert len(groups) == 64
    assert [[n["pitch"] for n in group] for group in groups] == EXPECTED
    assert all(
        len({n["start"] for n in g}) == len({n["end"] for n in g}) == 1 for g in groups
    )


def test_chords_do_not_need_song_vocabulary():
    y = np.zeros(SR * 3)
    expected = [[40, 45], [44, 49], [47, 52], [45, 50]]
    for start, pitches in zip([0.3, 0.9, 1.5, 2.1], expected):
        tone = sum(synth_pluck(p, 0.45, amplitude=0.2) for p in pitches)
        at = int(start * SR)
        y[at : at + len(tone)] += tone
    groups = group_events(transcribe_chords(y, SR))
    assert [[n["pitch"] for n in g] for g in groups] == expected


def test_automatic_grid_keeps_chords_pauses_and_every_event():
    notes = [
        {"pitch": p, "start": t, "end": t + 0.16, "velocity": 80}
        for t, ps in [
            (0, [40, 45]),
            (0.26, [44, 49]),
            (1.51, [47, 52]),
            (1.77, [40, 45]),
        ]
        for p in ps
    ]
    out = auto_fit_rhythm(notes, 120)
    groups = group_events(out)
    assert len(out) == len(notes) == 8
    assert [g[0]["start"] for g in groups] == [0, 0.25, 1.5, 1.75]
    assert groups[2][0]["start"] - groups[1][0]["start"] == 1.25
    assert all(len({n["end"] for n in g}) == 1 for g in groups)
    assert notes[2]["start"] == 0.26


def test_manual_rhythm_counts_chords_as_attacks():
    source = [
        {"pitch": p, "start": i * 0.3, "end": i * 0.3 + 0.2, "velocity": 80}
        for i in range(8)
        for p in [44, 49]
    ]
    fitted = fit_rhythm(source, 120, measures=1, notes_per_measure=8)
    assert len(fitted) == 16
    assert len(group_events(fitted)) == 8
    assert group_events(fitted)[-1][0]["start"] == 1.75
    assert assign_fingering([49, 54]) == {49: (6, 9), 54: (5, 9)}


def test_live_endpoint_is_bounded_and_does_not_create_projects(client):
    from src.backend import api

    y = np.zeros(SR * 3)
    for t in [0.4, 1.2, 2.0]:
        tone = synth_pluck(55, 0.4, amplitude=0.3)
        at = int(t * SR)
        y[at : at + len(tone)] += tone
    wav = io.BytesIO()
    sf.write(wav, y, SR, format="WAV")
    before = set(api.PROJECTS)
    response = client.post(
        "/live", files={"file": ("live.wav", wav.getvalue(), "audio/wav")}
    )
    assert response.status_code == 200
    assert [n["pitch"] for n in response.json()["notes"]] == [55, 55, 55]
    assert set(api.PROJECTS) == before
    assert (
        client.post(
            "/live", files={"file": ("bad.wav", b"bad", "audio/wav")}
        ).status_code
        == 422
    )
    wav = io.BytesIO()
    sf.write(wav, np.zeros(SR * 7), SR, format="WAV")
    assert (
        client.post(
            "/live", files={"file": ("long.wav", wav.getvalue(), "audio/wav")}
        ).status_code
        == 413
    )


def test_trim_auto_tempo_and_chord_exports(client):
    path = ROOT / "recordings/mitski.wav"
    if not path.exists():
        pytest.skip("Local recording missing")
    with path.open("rb") as audio:
        pid = client.post(
            "/upload", files={"file": ("mitski.wav", audio, "audio/wav")}
        ).json()["project_id"]
    response = client.post(
        f"/transcribe/{pid}?mode=chords&trim=true&tidy=true&target_bpm=100&subdivisions=4"
    )
    assert response.status_code == 200
    data = response.json()
    groups = group_events(data["tracks"]["Guitar"])
    assert len(groups) == 64 and groups[0][0]["start"] == 0
    assert data["audio_offset"] > 3 and data["rhythm"]["mode"] == "auto"
    assert [[n["pitch"] for n in g] for g in groups] == EXPECTED
    assert data["tablature"][0]["positions"] == [
        {"pitch": 44, "string": 6, "fret": 4},
        {"pitch": 49, "string": 5, "fret": 4},
    ]
    before = [g[0]["start"] for g in groups]
    result = client.post(f"/tempo/{pid}", json={"bpm": 200})
    assert result.status_code == 200
    assert [
        g[0]["start"] for g in group_events(result.json()["tracks"]["Guitar"])
    ] == pytest.approx([t / 2 for t in before])
    assert client.post(f"/playback/{pid}?mix_ratio=0.5").status_code == 422
    for format in ["musicxml", "tab"]:
        result = client.get(f"/sheet/{pid}?format={format}")
        root = ET.parse(result.json()["sheet_path"]).getroot()
        attacks = [
            n
            for n in root.findall(".//note")
            if n.find("pitch") is not None
            and not any(t.get("type") == "stop" for t in n.findall("tie"))
        ]
        assert len([n for n in attacks if n.find("chord") is not None]) == 64
        assert len(attacks) == 128
    result = client.post(f"/timing/{pid}", json={"bpm": 200, "automatic": False})
    assert result.status_code == 200 and result.json()["rhythm"] is None
