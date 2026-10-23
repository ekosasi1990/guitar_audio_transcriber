# Project interview guide

## The story

You started learning guitar and did not yet know how to write down what you
played. You wanted to save an improvised tune as tablature rather than rely
on remembering it. A second motivation was hearing guitar covers in short
videos that did not include tabs and wanting a playable version.

That is the motivation. The current implementation is strongest on isolated
guitar recordings; it does not extract a guitar from an arbitrary full mix.

### A 45-second pitch

“I started this when I was learning guitar. Sometimes I would play a tune I
liked but couldn't write it down, and I also wanted to learn guitar clips
that didn't include tabs. So I built a desktop tool that turns recordings
into notes and playable tablature.

It uses a JavaScript interface in Electron and a local Python audio service.
The challenging part was distinguishing a new pluck from a string that was
still ringing, then turning uneven playing into a useful rhythm. The result
is editable, so the user can correct timing, change tempo, hear the notes,
and export them to another music application.”

Practice this in your own words. Follow it with a recording rather than a
list of libraries.

### Explaining development and assistance

You said you started from scratch using Windsurf, then moved to ChatGPT.
An accurate answer if asked about tooling is:

“I used AI coding assistance, starting with Windsurf and later ChatGPT. I
defined the guitar use case, recorded examples, supplied expected note
sequences, and used those examples to identify problems with sustain,
repeated plucks, and rhythm. I used the tools to help implement and revise
the code. I can walk through the resulting pipeline and its tests.”

Only add claims about reviewing, debugging, or independently implementing
specific functions when they describe work you actually did. The strongest
preparation is being able to change a setting, explain its effect, and trace
that effect in the code. Do not claim to have trained Basic Pitch or written
the underlying YIN algorithm.

## Demo plan: about five minutes

| Time | Action | What to explain |
| --- | --- | --- |
| 0:00–0:45 | Give the pitch. | Personal need and the intended user. |
| 0:45–1:30 | Open Smooth in single-note mode. | Audio becomes 32 editable attacks, rather than a picture of a waveform. |
| 1:30–2:15 | Play the original under Advanced, then the transcription. | The original recording and synthesized note data are different representations. |
| 2:15–3:00 | Open Assign an intended rhythm manually; set 2 bars and 16 attacks per bar. | Intent can be ambiguous; users can tell the app the rhythm they meant. Four attacks per beat means 16 per 4/4 bar. |
| 3:00–3:30 | Change Playback BPM below the sheet and seek by clicking the sheet. | Listening speed changes without changing the transcription or exported notes. Clear the field to restore the transcription tempo. |
| 3:30–4:15 | Open Mitski in chord mode, with automatic spacing. | This sample contains 64 chord attacks and 128 individual pitches. Each chord shares timing. |
| 4:15–5:00 | Export MIDI or MusicXML, then summarize limits. | The output works outside the app. Explain what still needs broader validation. |

For Mitski, select Chords and Bottom 3 strings before opening the recording.
If you previously entered a target BPM, use Detect tempo. The same performed
spacing can be interpreted as quarter notes or eighth notes; halving the BPM
places twice as many attacks in each bar. This is a beat interpretation, not
two different performances.

Use recorded inputs as the main demo. A short live take is optional after
checking the actual microphone. Do not make the interview depend on recording
a perfect phrase or installing software during the call.

## Before screen sharing

1. Launch with `start.bat` and test sound through the same headphones/device
   you will use in the call. Confirm the call shares application audio.
2. Keep Smooth, Rough, and Mitski ready in `recordings/`. Check the note counts
   and make sure the detector mode matches each file.
3. Rehearse the sequence above once. Leave Advanced closed at the start and
   use it to explain one feature at a time.
4. Keep the repository, this guide, and the architecture diagram ready. Open
   the code files you plan to discuss before sharing.
5. Keep a screenshot and an exported MIDI as a fallback. If live capture fails,
   use a saved take and explain the capture path separately.

## Explain the structure in one minute

“The frontend handles recording, controls, and the note display. It sends
audio to a Python service through a local API. The audio-processing modules
find attacks and pitches, then separate rhythm fitting from note detection.
The sheet-music modules turn pitches into notation and playable string/fret
positions. Playback and export read the same edited notes. Tests check the
algorithms with known synthetic sounds and recordings I supplied.”

Use [architecture.md](architecture.md) for file-by-file details. In a code
walkthrough, open these in order:

1. `src/frontend/js/recorder.js`: samples, buffered snapshots, and WAV encoding.
2. `src/backend/api.py`: upload and transcription endpoints.
3. `src/backend/audio_processing/transcription.py`: detector selection.
4. `src/backend/audio_processing/melody_transcription.py`: new attacks versus sustain.
5. `src/backend/audio_processing/quantization.py`: grid snapping and manually assigned rhythm.
6. `src/backend/sheet_music/fingering.py`: playable tab assignment.
7. `tests/test_melody_generalization.py`: unrelated pitches, uneven playing, and changed key/speed.

You do not need to explain every constant. Explain the evidence each stage
uses and why the stages are separate.

## Technologies used and their role

| Technology | Role in this project | A simple explanation |
| --- | --- | --- |
| Python | Audio service and processing. | A practical environment for working with audio arrays and music libraries. |
| NumPy / SciPy | Array operations, spectral analysis, and filtering. | They make numerical work on thousands of sound samples manageable. |
| librosa | Loading/resampling, attack detection, YIN, and beat tracking. | Existing signal-processing tools form the building blocks of the detector. |
| FastAPI / Pydantic | Local endpoints and validated settings. | A clear boundary between the interface and the processing code. |
| Electron | Desktop window around the web interface. | A desktop app built with familiar web UI tools. |
| JavaScript / Canvas | Controls, note layout, playhead, and seeking. | The sheet is drawn from editable note events. |
| Web Audio / AudioWorklet | Microphone capture. | Audio samples are collected outside the main UI thread. |
| pretty_midi | MIDI creation and playback integration. | Notes become a standard sequence of pitch, time, and loudness instructions. |
| music21 | Measured MusicXML sheet and tab output. | Musical durations and measures are represented as notation. |
| soundfile / pydub | Audio read/write and MP3 conversion. | File formats are converted into samples the detector can analyze. |
| Basic Pitch | Optional pretrained polyphonic transcription. | A model alternative for overlapping notes, with cleanup still needed. |
| pytest / Node checks | Regression and recorder verification. | Known inputs make changes testable instead of relying only on listening. |
| Black / Prettier / GitHub Actions | Formatting and automated checks. | Contributors get consistent formatting and repeatable checks. |

FastAPI provides request validation and generated API docs; it does not make
CPU-heavy audio analysis asynchronous by itself. See its
[features documentation](https://fastapi.tiangolo.com/features/).
Electron context isolation separates the page from privileged APIs; the
app also disables Node integration in its renderer. See
[Electron's context isolation guide](https://www.electronjs.org/docs/latest/tutorial/context-isolation).

## Alternatives you can discuss

These are possible design alternatives, not a claim that you tried each one.
If asked what you evaluated, distinguish actual repository paths from options
you now understand. The repository contains DSP and Basic Pitch approaches.

| Alternative | What it could offer | Tradeoff for this project |
| --- | --- | --- |
| Largest FFT peak alone | A small baseline implementation. | Guitar harmonics can be louder than the fundamental; one peak cannot describe a chord or identify a new pluck. |
| YIN in librosa, used here | Fundamental estimation from repeating structure. | Designed for a fundamental pitch; chord detection needs another approach. |
| pYIN | Probabilistic pitch candidates and sequence decoding. | Worth evaluating for uncertain melody frames; it still estimates a fundamental rather than recovering every chord member. |
| Aubio | C-based onset, pitch, beat, and live-audio tools. | A candidate for a lower-latency capture-to-MIDI path; adopting it would require testing packaging and its effect on the existing detector. |
| Essentia | A broad C++ audio-analysis library with Python/JS bindings. | Useful for richer descriptors; more scope than the current guitar-focused pipeline needs. |
| Basic Pitch | Pretrained polyphonic audio-to-MIDI, already optional. | Adds a model/runtime and can require cleanup for sustain and harmonics. The local tests, rather than a generic model claim, should determine suitability. |
| Training a custom model | Potentially tailored to this guitar use case. | Would require labeled recordings, evaluation data, and model maintenance; the current project has not trained one. |
| Browser-only processing | No desktop installer or local Python service. | Would require moving or replacing the Python processing pipeline. |
| A native desktop UI | Could avoid shipping a browser runtime. | Would require replacing the existing web canvas and controls. |
| React instead of plain JS | More structured component/state management as the editor grows. | The current single-screen interface does not yet require another UI framework. |
| A cloud API | Centralized processing and shared projects. | Adds uploads, hosting, access control, and persistence; the present app is local. |

The pitch-method distinctions come from [YIN](https://librosa.org/doc/0.11.0/generated/librosa.yin.html)
and [pYIN](https://librosa.org/doc/0.11.0/generated/librosa.pyin.html).
Library capabilities are documented by [Aubio](https://aubio.org/),
[Essentia](https://essentia.upf.edu/), and [Spotify Basic Pitch](https://github.com/spotify/basic-pitch).
The project-specific tradeoffs in the table are design judgments, not measured
benchmarks against libraries that have not been tested here.

## Questions to rehearse

### Why is this harder than detecting a frequency?

A plucked string continues ringing and produces harmonics. A new attack can
occur while an old note remains audible. The app needs to decide both which
pitch is present and whether a new musical event began. For chords, it also
needs to avoid treating one note's harmonics as additional notes.

### What was a concrete failure and how was it addressed?

Use one example: a ringing string can be mistaken for another note or obscure
an intentional second pluck. The detector looks for new attack and harmonic
energy rather than relying only on pitch being present. Regression recordings
check pitch order and attack counts. Timing correction is a separate operation;
the current version uses grid snapping or a manually specified rhythm.

Another example is live snapshots retaining incorrect pitch guesses. The
preview now replaces a reliable overlapping region and waits for more audio
at window boundaries. Full-take analysis after Stop remains the final result.

### How do you test accuracy?

Synthetic audio has known pitches and attack times. Tests check event count,
pitch order, chord alignment, rests, exports, and API behavior. Local Smooth
and Rough have 32 expected attacks each; Mitski has 64 dyads. Volume-reduction
checks test relative cleanup. This is regression coverage, not proof of a
universal accuracy percentage. A broader evaluation would need independently
labeled performances, precision/recall, timing error, and several guitars.

### How does quantization work?

At 120 BPM, a quarter beat lasts 0.5 seconds and a sixteenth lasts 0.125.
Detected starts are rounded to the selected grid, with separate attacks kept
in separate slots. Clear pauses remain. The manual fitter can instead assign
attacks in order to an explicitly chosen number of bars and slots per bar.
That is a user-supplied rhythm, not guaranteed intent recognition. Swing,
triplets, and arbitrary rubato are not supported.

### How do you turn a pitch into a fret?

Subtract the open-string pitch from the detected pitch. Check the fret range,
then choose a playable assignment. Chords cannot put two pitches on the same
string. String filters narrow the choices, but identical pitches on different
strings remain acoustically ambiguous.

### Why does the playback sound different?

MIDI describes notes, not the original sound. The synth recreates those notes
with a guitar-like envelope. Pick noise, body resonance, bends, and other
details are not preserved. This playback is useful for checking the sequence,
not an exact reconstruction of the guitarist's tone.

### What would you improve next?

Persist projects so edits survive a restart, expand annotated test recordings,
and measure timing/chord accuracy. For a larger deployment, move processing
to workers and add access controls and limits. For guitar clips with backing
tracks, source separation would be a separate feature to evaluate.

### What is the business value?

“It turns a recording into something a beginner can inspect, replay slowly,
and practice. The editable output matters because transcription is uncertain:
the tool saves effort without hiding the need for correction.”

## A description that matches the current demo

- Developed a local desktop workflow for converting guitar recordings into
  editable note events, tablature, MIDI, and MusicXML.
- Combined attack analysis, fundamental/chord detection, tempo estimation,
  and editable rhythm fitting to handle repeated plucks and ringing strings.
- Connected note editing and a scrollable sheet to synthesized playback and
  export, with regression tests using synthetic and personal recordings.

Mention accompaniment as an earlier/backend capability if relevant. Do not
present the current UI as a complete multitrack instrument-assignment editor.

## Final practice exercise

Without the guide, explain what one note dictionary contains, why two plucks
of the same pitch must remain separate, what a sixteenth means at 120 BPM,
and why a G3 can appear on more than one string. Then open the corresponding
function and connect its inputs and output to that explanation.

If you can do that, you can show technical understanding through the project
instead of relying on a memorized list of technology names.
