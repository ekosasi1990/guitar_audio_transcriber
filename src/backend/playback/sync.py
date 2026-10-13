import os
import tempfile
import numpy as np
import soundfile as sf
import pretty_midi


def synthesize_midi(pm, sr):
    """Render a PrettyMIDI object to audio.

    Uses fluidsynth when a soundfont/synth is available, otherwise falls back
    to pretty_midi's built-in additive synthesizer (no external dependencies).
    """
    try:
        return pm.fluidsynth(fs=sr)
    except Exception:
        parts = [inst.synthesize(fs=sr) for inst in pm.instruments]
        n = max((len(p) for p in parts), default=0)
        out = np.zeros(n)
        for p in parts:
            out[: len(p)] += p
        return out


def render_synced_audio(original_wav, midi_path, output_path, mix_ratio=0.5):
    """
    Mix the original audio with a synthesized MIDI accompaniment.
    Returns the path to the mixed audio file.
    """
    y, sr = sf.read(original_wav)
    if y.ndim == 2:
        y = y.mean(axis=1)

    pm = pretty_midi.PrettyMIDI(midi_path)
    midi_audio = synthesize_midi(pm, sr)
    if len(midi_audio) > len(y):
        y = np.pad(y, (0, len(midi_audio) - len(y)), mode="constant")
    elif len(midi_audio) < len(y):
        midi_audio = np.pad(midi_audio, (0, len(y) - len(midi_audio)), mode="constant")

    mixed = (1 - mix_ratio) * y + mix_ratio * midi_audio
    mixed = np.clip(mixed, -1.0, 1.0)
    sf.write(output_path, mixed, sr)
    return output_path
