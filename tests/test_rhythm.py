import copy
import xml.etree.ElementTree as ET
from pathlib import Path

import pytest

from src.backend.audio_processing.quantization import fit_rhythm
from src.backend.sheet_music.staff import notes_to_musicxml


def uneven_notes(count=32):
    return [
        dict(
            pitch=54 if i % 2 else 55,
            start=1.0 + i * 0.53,
            end=1.0 + i * 0.53 + 0.265,
            velocity=80,
        )
        for i in range(count)
    ]


def test_even_rhythm_four_measures():
    source = uneven_notes()
    fitted = fit_rhythm(source, 120)
    assert [n["start"] for n in fitted] == [i * 0.25 for i in range(32)]
    assert [n["pitch"] for n in fitted] == [n["pitch"] for n in source]
    assert [n["velocity"] for n in fitted] == [80] * 32
    assert all(n["end"] - n["start"] == pytest.approx(0.125) for n in fitted)
    assert source[0]["start"] == 1.0


def test_custom_rhythm_and_tempo():
    notes = fit_rhythm(
        uneven_notes(10),
        60,
        measures=2,
        pattern=[1, 0.5, 0.5, 1, 1],
        articulation="connected",
    )
    assert [n["start"] for n in notes] == [0, 1, 1.5, 2, 3, 4, 5, 5.5, 6, 7]
    assert notes[-1]["end"] == 8


@pytest.mark.parametrize(
    "kwargs",
    [
        dict(measures=3),
        dict(pattern=[1, 1]),
        dict(pattern=[0, 4]),
        dict(pattern=[float("nan"), 4]),
    ],
)
def test_invalid_rhythm(kwargs):
    with pytest.raises(ValueError):
        fit_rhythm(uneven_notes(), 120, **kwargs)


def test_real_measures_and_accidentals(tmp_path):
    notes = fit_rhythm(uneven_notes(), 120)
    path = tmp_path / "fitted.musicxml"
    notes_to_musicxml({"Guitar": notes}, 120, str(path))
    root = ET.parse(path).getroot()
    measures = root.findall(".//part/measure")
    assert len(measures) == 4
    assert all(len(m.findall("note")) == 8 for m in measures)
    assert any(
        p.find("step").text == "F" and p.find("alter").text == "1"
        for p in root.findall(".//pitch")
        if p.find("alter") is not None
    )
    assert len(root.findall(".//staccato")) == 32


def test_api_fit_undo_and_validation(client, monkeypatch):
    from src.backend import api

    source = uneven_notes()
    monkeypatch.setitem(
        api.PROJECTS,
        "rhythm-test",
        {"tracks": {"Guitar": copy.deepcopy(source)}, "bpm": 57},
    )
    bad = client.post("/rhythm/rhythm-test", json={"bpm": 120, "measures": 3})
    assert bad.status_code == 422
    assert api.PROJECTS["rhythm-test"]["tracks"]["Guitar"] == source
    result = client.post("/rhythm/rhythm-test", json={"bpm": 120})
    assert result.status_code == 200
    assert result.json()["can_undo_rhythm"]
    assert result.json()["tracks"]["Guitar"][8]["start"] == 2
    assert client.post("/playback/rhythm-test?mix_ratio=0.5").status_code == 422
    result = client.post("/rhythm/rhythm-test/undo")
    assert result.status_code == 200
    assert result.json()["tracks"]["Guitar"] == source
    assert result.json()["bpm"] == 57
    assert not result.json()["can_undo_rhythm"]
    assert client.post("/rhythm/missing", json={"bpm": 120}).status_code == 404


def test_smooth_fit_export_and_playback(client):
    path = Path(__file__).resolve().parents[1] / "recordings" / "smooth.wav"
    if not path.exists():
        pytest.skip("Local smooth reference missing")
    with path.open("rb") as audio:
        pid = client.post(
            "/upload", files={"file": (path.name, audio, "audio/wav")}
        ).json()["project_id"]
    original = client.post(f"/transcribe/{pid}").json()["tracks"]["Guitar"]
    result = client.post(f"/rhythm/{pid}", json={"bpm": 120})
    assert result.status_code == 200
    fitted = result.json()["tracks"]["Guitar"]
    assert len(fitted) == 32
    assert [n["pitch"] for n in fitted] == [n["pitch"] for n in original]
    assert fitted[-1]["start"] == 7.75
    result = client.get(f"/sheet/{pid}")
    measures = (
        ET.parse(result.json()["sheet_path"]).getroot().findall(".//part/measure")
    )
    assert len(measures) == 4
    assert all(len(m.findall("note")) == 8 for m in measures)
    assert client.post(f"/export/{pid}").content[:4] == b"MThd"
    response = client.post(f"/playback/{pid}")
    assert response.status_code == 200
    import io
    import soundfile as sf

    y, sr = sf.read(io.BytesIO(response.content))
    assert 7.75 < len(y) / sr < 10
    assert client.post(f"/rhythm/{pid}/undo").json()["tracks"]["Guitar"] == original
