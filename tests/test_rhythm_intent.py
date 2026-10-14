from pathlib import Path
import io
import numpy as np
import pytest
import soundfile as sf
from src.backend.audio_processing.quantization import auto_fit_rhythm, group_events


def melody(starts, pitches=None, durations=None):
    pitches = pitches or [55] * len(starts)
    durations = durations or [0.05 if i % 2 == 0 else 0.10 for i in range(len(starts))]
    return [
        dict(pitch=p, start=t, end=t + d, velocity=80)
        for t, p, d in zip(starts, pitches, durations)
    ]


def test_sixteenth_jitter_is_one_recurring_interval_not_two_rounding_bins():
    gaps = [0.10, 0.17, 0.13, 0.11, 0.16, 0.12, 0.14] * 4
    starts = np.r_[0, np.cumsum(gaps)].tolist()
    source = melody(starts, [55 + i // 2 % 4 for i in range(len(starts))])
    fitted = auto_fit_rhythm(source, 120)
    assert len(fitted) == len(source)
    assert [n["start"] for n in fitted] == pytest.approx(
        [i * 0.125 for i in range(len(starts))], abs=1e-6
    )
    assert all(n["beat_duration"] == 0.25 for n in fitted)
    for i in range(0, len(fitted) - 1, 2):
        assert fitted[i]["end"] - fitted[i]["start"] == pytest.approx(
            fitted[i + 1]["end"] - fitted[i + 1]["start"]
        )
    assert source[-1]["start"] == starts[-1]


def test_pair_has_shared_length_even_when_the_second_is_followed_by_a_rest():
    source = melody(
        [0, 0.14, 0.52, 0.65, 1.02, 1.15],
        [55, 55, 54, 54, 57, 57],
        [0.03, 0.22, 0.07, 0.13, 0.05, 0.1],
    )
    fitted = auto_fit_rhythm(source, 120)
    assert [n["start"] for n in fitted] == pytest.approx(
        [0, 0.125, 0.5, 0.625, 1, 1.125]
    )
    for a, b in zip(fitted[::2], fitted[1::2]):
        assert a["beat_duration"] == b["beat_duration"] == 0.25
        assert a["end"] - a["start"] == pytest.approx(b["end"] - b["start"])
    assert fitted[1]["end"] < fitted[2]["start"]


def test_explicit_sixteenths_override_four_attack_chord_pattern():
    source = [
        dict(pitch=p, start=i * 0.3, end=i * 0.3 + 0.2, velocity=80)
        for i in range(32)
        for p in [40 + i // 4 % 4, 45 + i // 4 % 4]
    ]
    groups = group_events(auto_fit_rhythm(source, 120, intended_spacing="sixteenth"))
    assert len(groups) == 32
    assert [g[0]["start"] for g in groups] == pytest.approx(
        [i * 0.125 for i in range(32)]
    )
    assert all(n["beat_duration"] == 0.25 for g in groups for n in g)
    assert groups[16][0]["start"] == 2


def test_mixed_rhythm_and_clear_rests_are_retained():
    source = melody([0, 0.13, 0.37, 0.50, 1.50, 1.63], [55, 57, 59, 60, 62, 64])
    fitted = auto_fit_rhythm(source, 120)
    assert [n["start"] for n in fitted] == pytest.approx(
        [0, 0.125, 0.375, 0.5, 1.5, 1.625]
    )
    assert fitted[3]["end"] < 0.75


def test_keep_articulation_option_retains_different_lengths():
    fitted = auto_fit_rhythm(
        melody([0, 0.125, 0.25, 0.375]), 120, consistent_lengths=False
    )
    assert fitted[0]["end"] - fitted[0]["start"] != pytest.approx(
        fitted[1]["end"] - fitted[1]["start"]
    )


def test_save_in_project_recordings_without_overwriting(client, tmp_path, monkeypatch):
    from src.backend import api

    assert (
        Path(api.RECORDINGS_DIR).resolve()
        == Path(__file__).resolve().parents[1] / "recordings"
    )
    monkeypatch.setattr(api, "RECORDINGS_DIR", str(tmp_path / "recordings"))
    wav = io.BytesIO()
    sf.write(wav, np.zeros(1000), 22050, format="WAV")
    results = []
    for _ in range(2):
        r = client.post(
            "/recordings",
            data={"name": "demo"},
            files={"file": ("take.wav", wav.getvalue(), "audio/wav")},
        )
        assert r.status_code == 200
        path = Path(r.json()["path"])
        assert path.parent == tmp_path / "recordings"
        assert path.read_bytes() == wav.getvalue()
        results.append(path)
    assert results[0] != results[1]
    assert (
        client.post(
            "/recordings", files={"file": ("bad.wav", b"bad", "audio/wav")}
        ).status_code
        == 422
    )


def test_timing_intent_settings_apply_and_undo(client, monkeypatch):
    from src.backend import api

    source = melody([0, 0.10, 0.28, 0.4], [55, 55, 57, 57])
    monkeypatch.setitem(
        api.PROJECTS,
        "intent",
        {"tracks": {"Guitar": source}, "performed_notes": source, "bpm": 120},
    )
    result = client.post(
        "/timing/intent", json={"bpm": 120, "intended_spacing": "sixteenth"}
    ).json()
    assert result["rhythm"]["intended_spacing"] == "sixteenth"
    assert [n["start"] for n in result["tracks"]["Guitar"]] == pytest.approx(
        [0, 0.125, 0.25, 0.375]
    )
    assert client.post("/rhythm/intent/undo").json()["tracks"]["Guitar"] == source
    assert (
        client.post("/timing/intent", json={"intended_spacing": "invalid"}).status_code
        == 422
    )
