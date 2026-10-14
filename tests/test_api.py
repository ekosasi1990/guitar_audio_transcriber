"""API-level functional tests covering the core workflow:
upload -> transcribe -> edit/tracks -> export MIDI -> sheet/playback.
"""

import io
import xml.etree.ElementTree as ET

import pretty_midi


def _upload(client, wav_path):
    with open(wav_path, "rb") as f:
        res = client.post("/upload", files={"file": ("melody.wav", f, "audio/wav")})
    assert res.status_code == 200
    data = res.json()
    assert data["duration"] > 0
    return data["project_id"]


def _transcribe(client, project_id, **params):
    res = client.post(f"/transcribe/{project_id}", params=params)
    assert res.status_code == 200
    return res.json()


def test_upload_returns_project(client, melody_wav):
    pid = _upload(client, melody_wav)
    assert isinstance(pid, str) and pid


def test_transcribe_returns_note_events(client, melody_wav):
    pid = _upload(client, melody_wav)
    data = _transcribe(client, pid, quantize="false")
    assert data["bpm"] > 0
    guitar = data["tracks"]["Guitar"]
    assert len(guitar) > 0
    for n in guitar:
        assert set(n) >= {"pitch", "start", "end", "velocity"}
        assert 0 <= n["start"] < n["end"]
        assert 0 <= n["pitch"] <= 127


def test_transcribe_quantized_default(client, melody_wav):
    pid = _upload(client, melody_wav)
    data = _transcribe(client, pid)
    guitar = data["tracks"]["Guitar"]
    assert all(n["end"] > n["start"] for n in guitar)


def test_unknown_project_returns_404(client):
    assert client.post("/transcribe/does-not-exist").status_code == 404
    assert client.get("/tracks/does-not-exist").status_code == 404
    assert client.post("/export/does-not-exist").status_code == 404
    assert client.get("/sheet/does-not-exist").status_code == 404
    assert client.post("/playback/does-not-exist").status_code == 404


def test_get_tracks_after_transcribe(client, melody_wav):
    pid = _upload(client, melody_wav)
    _transcribe(client, pid)
    res = client.get(f"/tracks/{pid}")
    assert res.status_code == 200
    data = res.json()
    assert data["bpm"] > 0
    assert "Guitar" in data["tracks"]


def test_edit_note(client, melody_wav):
    pid = _upload(client, melody_wav)
    data = _transcribe(client, pid, quantize="false")
    note = data["tracks"]["Guitar"][0]
    edit = {
        "track": "Guitar",
        "old_pitch": note["pitch"],
        "old_start": note["start"],
        "new_pitch": note["pitch"] + 2,
        "new_start": note["start"] + 0.1,
        "new_end": note["end"] + 0.1,
        "new_velocity": 100,
    }
    res = client.post(f"/edit/{pid}", json=edit)
    assert res.status_code == 200
    updated = client.get(f"/tracks/{pid}").json()["tracks"]["Guitar"]
    match = [n for n in updated if abs(n["start"] - note["start"] - 0.1) < 0.01]
    assert match and match[0]["pitch"] == note["pitch"] + 2
    assert match[0]["velocity"] == 100


def test_edit_unknown_track_returns_404(client, melody_wav):
    pid = _upload(client, melody_wav)
    edit = {
        "track": "Nope",
        "old_pitch": 60,
        "old_start": 0.0,
        "new_pitch": 60,
        "new_start": 0.0,
        "new_end": 1.0,
        "new_velocity": 80,
    }
    assert client.post(f"/edit/{pid}", json=edit).status_code == 404


def test_export_returns_valid_midi(client, melody_wav):
    pid = _upload(client, melody_wav)
    _transcribe(client, pid)
    res = client.post(f"/export/{pid}")
    assert res.status_code == 200
    assert res.content[:4] == b"MThd"
    pm = pretty_midi.PrettyMIDI(io.BytesIO(res.content))
    guitar = [i for i in pm.instruments if not i.is_drum]
    assert guitar and len(guitar[0].notes) > 0


def test_accompaniment_adds_tracks(client, melody_wav):
    pid = _upload(client, melody_wav)
    _transcribe(client, pid)
    res = client.post(f"/accompaniment/{pid}", json={"chords": [[0, "C"], [4, "G"]]})
    assert res.status_code == 200
    tracks = res.json()["tracks"]
    assert {"Guitar", "Drums", "Bass", "Keyboard"} <= set(tracks)
    assert len(tracks["Drums"]) > 0


def test_sheet_musicxml(client, melody_wav):
    pid = _upload(client, melody_wav)
    _transcribe(client, pid)
    res = client.get(f"/sheet/{pid}?format=musicxml")
    assert res.status_code == 200
    path = res.json()["sheet_path"]
    root = ET.parse(path).getroot()
    assert root.tag == "score-partwise"
    assert root.findall(".//note")


def test_save_recording_to_repo_dir(client, melody_wav, tmp_path, monkeypatch):
    from src.backend import api

    monkeypatch.setattr(api, "RECORDINGS_DIR", str(tmp_path))
    with open(melody_wav, "rb") as f:
        res = client.post(
            "/recordings",
            files={"file": ("take.wav", f, "audio/wav")},
            data={"name": "mytake"},
        )
    assert res.status_code == 200
    data = res.json()
    assert data["filename"] == "mytake.wav"
    assert (tmp_path / "mytake.wav").exists()


def test_sheet_tablature(client, melody_wav):
    pid = _upload(client, melody_wav)
    _transcribe(client, pid)
    res = client.get(f"/sheet/{pid}?format=tab")
    assert res.status_code == 200
    path = res.json()["sheet_path"]
    root = ET.parse(path).getroot()
    assert root.tag == "score-partwise"
