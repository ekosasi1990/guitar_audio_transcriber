"""Functional tests for MIDI export: the file must parse and carry the
expected notes, tempo, and instrument assignments."""
import os

import pretty_midi

from src.backend.audio_processing.midi_export import export_midi


def _roundtrip(tmp_path, tracks, bpm=120.0, instruments=None, accompaniment=None):
    out = str(tmp_path / "out.mid")
    export_midi(tracks, bpm, instruments or {}, out, accompaniment=accompaniment)
    assert os.path.exists(out)
    with open(out, "rb") as f:
        assert f.read(4) == b"MThd"
    return pretty_midi.PrettyMIDI(out)


def test_export_midi_roundtrip(tmp_path):
    tracks = {
        "Guitar": [
            {"pitch": 64, "start": 0.0, "end": 0.5, "velocity": 90},
            {"pitch": 67, "start": 0.5, "end": 1.0, "velocity": 80},
        ]
    }
    pm = _roundtrip(tmp_path, tracks, bpm=120.0, instruments={"Guitar": 25})

    assert len(pm.instruments) == 1
    inst = pm.instruments[0]
    assert inst.program == 25
    assert not inst.is_drum
    assert len(inst.notes) == 2

    by_pitch = {n.pitch: n for n in inst.notes}
    assert set(by_pitch) == {64, 67}
    assert abs(by_pitch[64].start - 0.0) < 0.01
    assert abs(by_pitch[64].end - 0.5) < 0.01
    assert by_pitch[64].velocity == 90

    # Tempo map should encode ~120 BPM.
    _, tempi = pm.get_tempo_changes()
    assert abs(tempi[0] - 120.0) < 1.0


def test_export_midi_empty_track(tmp_path):
    # pretty_midi omits instruments with no notes when writing; the file must
    # still be a valid, parseable MIDI.
    pm = _roundtrip(tmp_path, {"Guitar": []})
    assert sum(len(i.notes) for i in pm.instruments) == 0


def test_export_midi_drum_accompaniment(tmp_path):
    accomp = {
        "Drums": [{"pitch": 36, "start": 0.0, "end": 0.05, "velocity": 100}],
        "Bass": [{"pitch": 36, "start": 0.0, "end": 0.5, "velocity": 90}],
    }
    pm = _roundtrip(tmp_path, {"Guitar": []}, accompaniment=accomp)
    drums = [i for i in pm.instruments if i.is_drum]
    assert len(drums) == 1
    assert drums[0].name == "Drums"
    assert drums[0].notes[0].pitch == 36
