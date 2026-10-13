"""Neural transcription via Spotify's Basic Pitch model (ONNX runtime).

basic-pitch is an optional dependency; transcribe_neural raises ImportError
when it is not installed so callers can fall back to the DSP pipeline.
"""
import logging

_model = None


def _get_model():
    global _model
    if _model is None:
        from basic_pitch import ICASSP_2022_MODEL_PATH
        from basic_pitch.inference import Model

        logging.info("Loading Basic Pitch model from %s", ICASSP_2022_MODEL_PATH)
        _model = Model(ICASSP_2022_MODEL_PATH)
    return _model


def transcribe_neural(audio_path, min_freq=75.0, max_freq=1500.0,
                      onset_threshold=0.6, frame_threshold=0.4,
                      minimum_note_length=140.0):
    """Return flat note dicts [{pitch, start, end, velocity}] for audio_path.

    Thresholds are tuned for picked guitar: a higher onset threshold means
    only real pluck attacks spawn notes, and a higher frame threshold means
    decaying sustain does not re-articulate as octave/harmonic notes.
    """
    from basic_pitch.inference import predict

    _, _, note_events = predict(
        audio_path,
        _get_model(),
        onset_threshold=onset_threshold,
        frame_threshold=frame_threshold,
        minimum_note_length=minimum_note_length,
        minimum_frequency=min_freq,
        maximum_frequency=max_freq,
        melodia_trick=True,
    )
    notes = []
    for start_s, end_s, pitch, confidence, _bends in note_events:
        if end_s <= start_s:
            continue
        notes.append({
            "pitch": int(round(pitch)),
            "start": float(start_s),
            "end": float(end_s),
            "velocity": max(1, min(127, int(round(confidence * 127)))),
        })
    return _merge_retriggered(notes)


def _merge_retriggered(notes, max_gap=0.08):
    """Merge a note with a same-pitch re-trigger that starts almost
    immediately after it ended (sustain tail re-articulation)."""
    out = []
    for n in sorted(notes, key=lambda n: (n["start"], n["pitch"])):
        prev = out[-1] if out else None
        if (prev and prev["pitch"] == n["pitch"]
                and 0 <= n["start"] - prev["end"] <= max_gap):
            prev["end"] = n["end"]
            prev["velocity"] = max(prev["velocity"], n["velocity"])
        else:
            out.append(dict(n))
    return out
