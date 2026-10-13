# Guitar Audio Transcriber

A desktop application that converts MP3 and WAV guitar recordings into editable MIDI note events using polyphonic pitch detection, onset analysis, tempo estimation, and rhythmic quantization.

## Features

- **Audio Processing Pipeline**: Load MP3/WAV guitar recordings and extract polyphonic notes using onset detection and pitch tracking.
- **Multitrack Editor**: Modify note pitch, timing, duration, tempo, and instrument assignments.
- **Accompaniment**: Automatically add drum, bass, and keyboard accompaniment tracks.
- **Playback**: Synchronized audio playback with the generated MIDI timeline.
- **Notation**: Sheet music and guitar tablature generation with MusicXML / MIDI export.
- **MIDI Export**: Export edited notes and accompaniment to standard `.mid` files.

## Architecture

- **Backend**: Python 3.11+ (FastAPI, librosa, pretty_midi, music21, soundfile)
- **Frontend**: Electron desktop application (HTML5 canvas, vanilla JavaScript)
- **Communication**: REST API between the Electron frontend and the Python backend

## Getting Started

### One-time setup (Windows)

Double-click `setup.bat` or run in Command Prompt:

```cmd
setup.bat
```

This installs Python and Node dependencies. To install into a virtual
environment instead of the system Python:

```cmd
python -m venv .venv
.venv\Scripts\activate
python -m pip install -r requirements.txt
npm install
```

> **Python 3.13+ note:** `pydub` (used only for MP3 import) relies on the
> `audioop` stdlib module that was removed in Python 3.13. The `audioop-lts`
> backport is installed automatically via `requirements.txt`. MP3 decoding
> additionally requires `ffmpeg` on PATH; WAV files need neither.

### Neural transcription (recommended)

By default the app transcribes with **Spotify Basic Pitch** (polyphonic
neural model, ONNX runtime — no GPU needed). If it isn't installed, the app
silently falls back to a much weaker onset+piptrack DSP pipeline.

```cmd
python -m pip install -r requirements-ml.txt
python -m pip install --no-deps basic-pitch
```

(`--no-deps` is required because upstream `basic-pitch` pins `numpy<1.24`,
which cannot build on Python 3.13+; the code itself works fine with newer
numpy.)

### Launch the app (Windows)

Double-click `start.bat` or run in Command Prompt:

```cmd
start.bat
```

This opens two windows: the FastAPI backend and the Electron frontend.

### Manual start

If you prefer to start manually:

```cmd
python -m uvicorn src.backend.api:app --reload
```

(or, inside the venv: `.venv\Scripts\python -m uvicorn src.backend.api:app`)

And in another Command Prompt:

```cmd
npm start
```

The interactive API docs are available at `http://127.0.0.1:8000/docs`.

## Running the tests

```cmd
python -m pip install -r requirements-dev.txt
python -m pytest tests
```

Tests use deterministic synthetic WAV fixtures (pure tones with known pitches
and onsets). Functional tests live in `test_api.py`, `test_audio_processing.py`,
and `test_midi_export.py`. `test_accuracy.py` is marked `accuracy` and is a
loose regression benchmark, not a correctness gate:

```cmd
python -m pytest tests -m accuracy   # benchmark only
python -m pytest tests -m "not accuracy"  # functional tests only
```

## Usage

1. Launch the app (`start.bat` or the installed `.exe` installer).
2. Import an MP3 / WAV file or record guitar directly with your microphone.
3. Click **Transcribe** to detect notes.
4. Review and edit detected notes in the multitrack editor.
5. Add accompaniment tracks if desired.
6. Export the result to MIDI or view sheet music / tablature.

## Known limitations

- **Transcription quality depends on the engine.** With Basic Pitch installed
  (see setup), polyphonic note detection is quite good for solo guitar. The
  built-in DSP fallback (onset detection + `librosa.piptrack`) works only on
  clean monophonic material and produces spurious partials on real recordings.
  No source separation is performed — mixed-instrument audio is not supported.
- **Playback synthesis is crude** — the fallback synthesizer is a simple
  additive synth. Install FluidSynth + a General MIDI soundfont for better
  playback sound.
- **DSP fallback misses pitches below ~150 Hz** (`piptrack` floor is 75 Hz but
  reliable detection needs ~150+); Basic Pitch does not have this limitation.
- **Tempo estimation is unreliable** on rubato or atypical audio; it falls
  back to 120 BPM when the tracker fails, which also affects quantization and
  note durations in notation export.
- **MP3 import** requires `pydub` + `ffmpeg`. WAV works with no extra setup.
- **Playback mixing** uses FluidSynth when a soundfont is installed; otherwise
  it falls back to a built-in additive synthesizer (crude sine-based sound).
- **Sheet/tablature export** writes a single un-measured part; rhythms are
  snapped to the nearest notatable value. Tablature carries string/fret
  technical annotations but is not a full tab staff layout.
- **In-memory project store**: projects are lost on backend restart, and there
  is no authentication — the API listens on localhost only.

## Building a Windows Installer

To create a single `.exe` installer that bundles both the Python backend and the Electron frontend:

```cmd
build-all.bat
```

This produces a `dist/Guitar Audio Transcriber Setup.exe` installer. The installer includes a `dist-backend/gat-backend/gat-backend.exe` which the frontend launches automatically on startup.

Because the backend includes audio / ML libraries, the installed app will be several hundred MB. The build excludes unused GUI toolkits (`tkinter`, `PyQt*`, `PySide*`, `wx`) to keep it as small as possible.

## License

MIT
