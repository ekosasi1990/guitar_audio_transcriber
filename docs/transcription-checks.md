# Transcription checks

## What went wrong in the October 14 takes

The latest take had 32 played notes but the detector returned 30. A fixed
clean-harmonic score rejected a real G3 repluck. A later F#3 was tracked as
F#2 by YIN and then rejected by the same score cutoff. Ringing strings also
created spectral-flux peaks that were not new plucks. These are detection
errors before rhythm fitting or tablature assignment.

## Changes

- Require a local rise in short-window RMS energy as well as spectral flux.
  This rejects release noises and changes in a decaying string's partials.
- Compare cleaned harmonic evidence with the candidate's own harmonic score,
  rather than using a fixed score calibrated to particular recording levels.
- Resolve disagreement between YIN and new harmonic energy with relative
  scores. Keep genuine low fundamentals with odd partials; reject an unsupported
  lower octave when the new upper pitch has stronger evidence.
- Keep relative loudness cleanup. Quiet residual strings should not pass
  solely because log-compressed harmonic scores look convincing.

The detector receives samples, sample rate, and cleanup strength. It does not
receive filenames, expected note counts, tablature, or the reference sequences.
Expected sequences appear only in tests. Rhythm fitting remains a later step;
these changes do not invent notes to fill bars.

The separate short-window path remains necessary for quick attacks; longer
windows resolve lower fundamentals. This patch changes the slower melody path
and leaves chord detection intact.

## Verification

| Recording | Required result | Result |
| --- | --- | --- |
| Smooth | 32 attacks, exact melody | Pass |
| Rough | 32 attacks, exact melody | Pass |
| take-20261014-124828-940576 | 32 attacks, exact melody | Pass |
| take-20261014-124519-686597 | 32 attacks, exact melody | Pass |
| Mitski, chord mode | 64 attacks, 128 pitches, exact dyads | Pass |

These recordings are also checked at one tenth of their original level.
Additional tests use unrelated randomly generated pitches, repeated plucks,
uneven timing, background noise, and 160–700 ms spacing. Smooth and the latest
take also pass after resampling changes both key and speed by two semitones
in either direction. Tests assert the complete pitch sequence, not just count.

## Limits

Passing these examples does not establish accuracy for every song or guitar.
Stress tests with strong overlapping unrelated tones still produce errors in
melody mode. Transposed Rough recordings also expose remaining errors. These
are useful future benchmarks rather than evidence of universal accuracy.
The original Smooth, Rough, and Mitski recordings are unchanged.

Local recordings are excluded from Git. Their tests skip when the source
files are absent; synthetic regression tests remain runnable in a fresh clone.

## References

- [Librosa onset detection](https://librosa.org/doc/0.11.0/_modules/librosa/onset.html):
  spectral peak picking and energy-based backtracking.
- [Librosa YIN](https://librosa.org/doc/main/api/generated/librosa.yin.html):
  autocorrelation-based fundamental-frequency estimation.
