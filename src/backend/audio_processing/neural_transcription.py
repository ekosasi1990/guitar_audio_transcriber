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


def transcribe_neural(audio_path, min_freq=75.0, max_freq=1500.0):
    """Return flat note dicts [{pitch, start, end, velocity}] for audio_path."""
    from basic_pitch.inference import predict

    _, _, note_events = predict(
        audio_path,
        _get_model(),
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
    notes.sort(key=lambda n: (n["start"], n["pitch"]))
    return notes
