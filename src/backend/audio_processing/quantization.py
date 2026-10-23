import math


def group_events(notes, tolerance=0.06):
    groups = []
    for note in sorted(notes, key=lambda n: (n["start"], n["pitch"])):
        if groups and note["start"] - groups[-1][0]["start"] <= tolerance:
            groups[-1].append(note)
        else:
            groups.append([note])
    return groups


def auto_fit_rhythm(
    notes, bpm, subdivisions=4, beats_per_measure=4, recognize_patterns=True
):
    """Snap performed events to a fixed beat grid, retaining rests and chord stacks."""
    groups = group_events(notes)
    if recognize_patterns:
        from .tempo_estimation import repeated_pattern

        pattern = repeated_pattern(notes, beats_per_measure)
        if pattern:
            out = []
            pulse = 60 / bpm
            for i, group in enumerate(groups):
                old_start = group[0]["start"]
                old_spacing = (
                    groups[i + 1][0]["start"] - old_start
                    if i + 1 < len(groups)
                    else groups[i][0]["start"] - groups[i - 1][0]["start"]
                )
                gate = min(
                    1,
                    max(0.1, (max(n["end"] for n in group) - old_start) / old_spacing),
                )
                for note in group:
                    out.append(
                        {
                            **note,
                            "start": i * pulse,
                            "end": (i + gate) * pulse,
                            "beat_duration": 1.0,
                        }
                    )
            return out
    step = 60 / bpm / subdivisions
    out, previous_start = [], -step
    for i, group in enumerate(groups):
        source_start = min(n["start"] for n in group)
        start = max(round(source_start / step) * step, previous_start + step)
        original_end = max(n["end"] for n in group)
        next_start = groups[i + 1][0]["start"] if i + 1 < len(groups) else original_end
        sounding = max(0.01, min(original_end, next_start) - source_start)
        span = max(step, next_start - source_start)
        slots = max(1, round(min(span, sounding / 0.65) / step))
        end = start + min(sounding, slots * step)
        if i + 1 < len(groups):
            next_grid = max(round(next_start / step) * step, start + step)
            end = min(end, next_grid)
            slots = min(slots, max(1, round((next_grid - start) / step)))
        for note in group:
            out.append(
                {
                    **note,
                    "start": round(start, 6),
                    "end": round(max(start + 0.01, end), 6),
                    "beat_duration": slots / subdivisions,
                }
            )
        previous_start = start
    return out


def fit_rhythm(
    notes,
    bpm,
    measures=4,
    beats_per_measure=4,
    notes_per_measure=8,
    pattern=None,
    articulation="preserve",
):
    """Assign notes in order to intended beat slots, independent of played timing."""
    pattern = pattern or [beats_per_measure / notes_per_measure] * notes_per_measure
    if any(not math.isfinite(v) or v <= 0 for v in pattern):
        raise ValueError("Pattern durations must be positive beat lengths.")
    if any(not math.isclose(v * 4, round(v * 4), abs_tol=1e-6) for v in pattern):
        raise ValueError(
            "Use beat lengths in quarter-beat steps (0.25, 0.5, 0.75, 1, …)."
        )
    if not math.isclose(sum(pattern), beats_per_measure, abs_tol=1e-6):
        raise ValueError(f"Pattern must total {beats_per_measure} beats per measure.")
    source_groups = group_events(notes)
    expected = measures * len(pattern)
    if len(source_groups) != expected:
        raise ValueError(
            f"This rhythm needs {expected} notes; the track has {len(source_groups)} attacks. Adjust measures or notes per measure."
        )
    source = [
        dict(group[0], end=max(n["end"] for n in group)) for group in source_groups
    ]
    result, beat = [], 0.0
    for i, note in enumerate(source):
        duration = pattern[i % len(pattern)]
        if articulation == "preserve":
            spacing = (
                source[i + 1]["start"] - note["start"]
                if i + 1 < len(source)
                else (
                    source[-1]["start"] - source[-2]["start"]
                    if len(source) > 1
                    else note["end"] - note["start"]
                )
            )
            gate = min(1.0, max(0.1, (note["end"] - note["start"]) / spacing))
        else:
            gate = 0.65 if articulation == "staccato" else 1.0
        start = beat * 60 / bpm
        for member in source_groups[i]:
            result.append(
                {
                    **member,
                    "start": start,
                    "end": start + duration * 60 / bpm * gate,
                    "beat_duration": duration,
                }
            )
        beat += duration
    return result


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
        quantized.append(
            {
                "pitch": note["pitch"],
                "start": round(q_start, 4),
                "end": round(max(q_end, q_start + step), 4),
                "velocity": note.get("velocity", 80),
            }
        )
    return quantized
