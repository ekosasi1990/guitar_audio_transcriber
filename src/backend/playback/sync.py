import numpy as np
import soundfile as sf
import pretty_midi
import librosa


def synthesize_midi(pm, sr):
    """Render a PrettyMIDI object to audio.

    Uses fluidsynth when a soundfont/synth is available, otherwise falls back
    to pretty_midi's built-in additive synthesizer (no external dependencies).
    """
    try:
        return pm.fluidsynth(fs=sr)
    except Exception:
        parts = []
        for inst in pm.instruments:
            if inst.is_drum or inst.program != 25:
                parts.append(inst.synthesize(fs=sr))
                continue
            part = np.zeros(int((pm.get_end_time() + 0.1) * sr))
            for note in inst.notes:
                start = int(note.start * sr)
                count = max(1, int((note.end - note.start) * sr))
                t = np.arange(count) / sr
                frequency = pretty_midi.note_number_to_hz(note.pitch)
                tone = sum(
                    np.sin(2 * np.pi * frequency * k * t) / k**2
                    for k in range(1, 5)
                    if frequency * k < sr / 2
                )
                envelope = (1 - np.exp(-t / 0.003)) * np.exp(-t / 0.45)
                release = min(count, int(sr * 0.025))
                envelope[-release:] *= np.linspace(1, 0, release)
                part[start : start + count] += (
                    tone * envelope * note.velocity / 127 * 0.35
                )
            parts.append(part)
        n = max((len(p) for p in parts), default=0)
        out = np.zeros(n)
        for p in parts:
            out[: len(p)] += p
        return out


def render_synced_audio(
    original_wav, midi_path, output_path, mix_ratio=0.5, original_offset=0
):
    """
    Mix the original audio with a synthesized MIDI accompaniment.
    Returns the path to the mixed audio file.
    """
    y, sr = librosa.load(original_wav, sr=None, mono=True)
    y = y[int(original_offset * sr) :]

    pm = pretty_midi.PrettyMIDI(midi_path)
    midi_audio = synthesize_midi(pm, sr)
    peak = np.max(np.abs(midi_audio), initial=0)
    if peak > 0:
        midi_audio = midi_audio * (0.85 / peak)
    if mix_ratio == 1:
        sf.write(output_path, midi_audio, sr)
        return output_path
    if len(midi_audio) > len(y):
        y = np.pad(y, (0, len(midi_audio) - len(y)), mode="constant")
    elif len(midi_audio) < len(y):
        midi_audio = np.pad(midi_audio, (0, len(y) - len(midi_audio)), mode="constant")

    mixed = (1 - mix_ratio) * y + mix_ratio * midi_audio
    mixed = np.clip(mixed, -1.0, 1.0)
    sf.write(output_path, mixed, sr)
    return output_path
