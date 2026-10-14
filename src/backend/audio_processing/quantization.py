import math
from statistics import median


def group_events(notes, tolerance=0.06):
    groups = []
    for note in sorted(notes, key=lambda n: (n["start"], n["pitch"])):
        if groups and note["start"] - groups[-1][0]["start"] <= tolerance:
            groups[-1].append(note)
        else:
            groups.append([note])
    return groups


def _consistent_lengths(notes, bpm):
    """Use a shared articulation for repeated voicings of the same beat length."""
    groups = group_events(notes)
    gates = {}
    for group in groups:
        n = group[0]
        key = (tuple(sorted(n["pitch"] for n in group)), n["beat_duration"])
        gate = (n["end"] - n["start"]) / (n["beat_duration"] * 60 / bpm)
        gates.setdefault(key, []).append(gate)
    out = []
    for group in groups:
        n = group[0]
        key = (tuple(sorted(n["pitch"] for n in group)), n["beat_duration"])
        gate = min(1, max(0.15, median(gates[key])))
        for member in group:
            out.append(
                {
                    **member,
                    "end": member["start"] + n["beat_duration"] * 60 / bpm * gate,
                }
            )
    return out


def _interval_slots(gaps, step, intended_spacing):
    """Cluster recurring gaps before assigning durations; accumulate musical slots.

    Similar gaps share a duration instead of straddling different rounding
    thresholds. Clearly longer gaps retain their separate rhythm/rest slots.
    """
    if not gaps:
        return []
    if intended_spacing != "auto":
        typical = median(gaps)
        return [
            max(1, round(gap / typical)) if gap >= typical * 1.8 else 1 for gap in gaps
        ]
    clusters = []
    for i, gap in sorted(enumerate(gaps), key=lambda item: item[1]):
        if clusters and gap / clusters[-1][0][1] <= 1.65:
            clusters[-1].append((i, gap))
        else:
            clusters.append([(i, gap)])
    slots = [1] * len(gaps)
    for cluster in clusters:
        duration = median(gap for _, gap in cluster)
        for i, gap in cluster:
            # Isolated intervals still round independently; recurring values
            # provide stronger evidence of the player's intended rhythm.
            slots[i] = max(1, round((duration if len(cluster) >= 2 else gap) / step))
    return slots


def auto_fit_rhythm(
    notes,
    bpm,
    subdivisions=4,
    beats_per_measure=4,
    recognize_patterns=True,
    intended_spacing="auto",
    consistent_lengths=True,
):
    """Snap performed events to a fixed beat grid, retaining rests and chord stacks."""
    groups = group_events(notes)
    if recognize_patterns and intended_spacing == "auto":
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
            return _consistent_lengths(out, bpm) if consistent_lengths else out
    units = {"sixteenth": 0.25, "eighth": 0.5, "quarter": 1}
    step = 60 / bpm * units.get(intended_spacing, 1 / subdivisions)
    gaps = [b[0]["start"] - a[0]["start"] for a, b in zip(groups, groups[1:])]
    spacing = _interval_slots(gaps, step, intended_spacing)
    repeated_lengths = {}
    if consistent_lengths:
        voicings = [tuple(sorted(n["pitch"] for n in group)) for group in groups]
        begin = 0
        for i in range(1, len(groups) + 1):
            if i == len(groups) or voicings[i] != voicings[begin]:
                if i - begin >= 2:
                    length = max(1, round(median(spacing[begin : i - 1])))
                    repeated_lengths.update({j: length for j in range(begin, i)})
                begin = i
    out = []
    cursor = round(groups[0][0]["start"] / step) * step if groups else 0
    for i, group in enumerate(groups):
        source_start = min(n["start"] for n in group)
        start = cursor
        original_end = max(n["end"] for n in group)
        next_start = groups[i + 1][0]["start"] if i + 1 < len(groups) else original_end
        sounding = max(0.01, min(original_end, next_start) - source_start)
        slots = (
            spacing[i]
            if i < len(spacing)
            else (spacing[-1] if spacing else max(1, round(sounding / step)))
        )
        slots = repeated_lengths.get(i, slots)
        span = max(0.01, gaps[i] if i < len(gaps) else gaps[-1] if gaps else sounding)
        gate = min(1, max(0.1, sounding / span))
        end = start + slots * step * gate
        # A clear release well before a long gap indicates a rest, not a
        # note held for the entire gap. Keep the following attack position.
        if i not in repeated_lengths and slots > 1 and sounding < span * 0.55:
            slots = max(1, round(sounding / step))
            end = start + min(sounding, slots * step)
        for note in group:
            out.append(
                {
                    **note,
                    "start": round(start, 6),
                    "end": round(max(start + 0.01, end), 6),
                    "beat_duration": round(slots * step * bpm / 60, 8),
                }
            )
        cursor += (spacing[i] if i < len(spacing) else slots) * step
    return _consistent_lengths(out, bpm) if consistent_lengths else out


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
