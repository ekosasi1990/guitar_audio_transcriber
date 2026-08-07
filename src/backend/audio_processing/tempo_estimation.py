import librosa
import numpy as np


def estimate_tempo(y, sr):
    """Estimate BPM and beat times using librosa's beat tracker."""
    tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
    beat_times = librosa.frames_to_time(beat_frames, sr=sr)
    if not beat_times.size:
        beat_times = np.arange(0.0, len(y) / sr, 60.0 / 120.0)
    if isinstance(tempo, np.ndarray):
        tempo = float(tempo[0])
    else:
        tempo = float(tempo)
    return tempo, beat_times.tolist()
