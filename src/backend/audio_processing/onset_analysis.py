import librosa
import numpy as np


def detect_onsets(y, sr):
    """Detect note onsets and offsets from an audio signal."""
    onset_env = librosa.onset.onset_strength(y=y, sr=sr)
    onsets = librosa.onset.onset_detect(
        onset_envelope=onset_env,
        sr=sr,
        units="time",
        backtrack=True,
        pre_max=20,
        post_max=20,
        pre_avg=100,
        post_avg=100,
        delta=0.2,
        wait=20,
    )
    # Estimate offsets by finding the next onset or a silence threshold.
    offsets = list(onsets[1:]) + [len(y) / sr]
    return np.array(onsets), np.array(offsets)
