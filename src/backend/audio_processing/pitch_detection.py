import numpy as np
import librosa


def detect_pitches(y, sr, onsets, offsets):
    """
    Polyphonic pitch detection per note segment.
    Uses librosa piptrack for multi-pitch estimation and returns a list of
    (start, end, [pitches]) tuples.
    """
    hop_length = 512
    pitches, magnitudes = librosa.piptrack(
        y=y,
        sr=sr,
        hop_length=hop_length,
        threshold=0.2,
        fmin=75.0,
        fmax=1500.0,  # cover low E (~82 Hz) up to ~fret 17 high E
    )
    times = librosa.frames_to_time(
        np.arange(pitches.shape[1]), sr=sr, hop_length=hop_length
    )

    notes = []
    for start, end in zip(onsets, offsets):
        frame_mask = (times >= start) & (times < end)
        segment_indices = np.where(frame_mask)[0]
        if len(segment_indices) == 0:
            continue

        segment_pitches = set()
        for idx in segment_indices:
            active = np.where(magnitudes[:, idx] > 0)[0]
            for bin_idx in active[:6]:  # cap at 6 simultaneous pitches
                if pitches[bin_idx, idx] > 0:
                    midi = int(round(librosa.hz_to_midi(pitches[bin_idx, idx])))
                    if 24 <= midi <= 104:
                        segment_pitches.add(midi)

        if segment_pitches:
            # Clean with median filter over pitch contour
            pitch_list = sorted(segment_pitches)
            notes.append(
                {
                    "start": float(start),
                    "end": float(end),
                    "pitches": pitch_list,
                }
            )

    # Each segment starts at a detected attack, including repeated pitches.
    return notes
