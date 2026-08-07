import math


def quantize_notes(notes, bpm, subdivisions=4, strength=1.0):
    """
    Quantize note start and end times to a musical grid.
    subdivisions: number of grid points per beat (4 = sixteenth notes).
    strength: 0.0 to 1.0, amount of quantization applied.
    """
    spb = 60.0 / bpm
    step = spb / subdivisions

    quantized = []
    for note in notes:
        start = note["start"]
        end = note["end"]
        q_start = round(start / step) * step
        q_end = round(end / step) * step
        if q_end <= q_start:
            q_end = q_start + step
        q_start = start + (q_start - start) * strength
        q_end = end + (q_end - end) * strength
        quantized.append({
            "pitch": note["pitch"],
            "start": round(q_start, 4),
            "end": round(max(q_end, q_start + step), 4),
            "velocity": note.get("velocity", 80),
        })
    return quantized
