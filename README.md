# Guitar Audio Transcriber

A local desktop app for turning guitar recordings into editable notes and
playable tablature. Open a WAV or MP3, or record through a microphone, then
review the notes, adjust the rhythm, and export MIDI or MusicXML.

I started this after picking up guitar. I wanted a way to write down tunes I
improvised and work out guitar clips that did not include tabs.

## Setup and launch

Install Python 3.11 or newer and Node.js 20 or newer. On Windows:

```cmd
setup.bat
start.bat
```

Setup creates `.venv` and installs the Python and desktop dependencies. The
launcher starts the local audio service and opens Electron. You can create a
desktop shortcut to `start.bat`; keep the batch file in the project folder.

For manual setup:

```cmd
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements-dev.txt
npm ci
```

For development, run these in separate terminals:

```cmd
.venv\Scripts\python -m uvicorn src.backend.api:app --reload
npm start
```

The API documentation is at `http://127.0.0.1:8000/docs`. MP3 decoding needs
FFmpeg on PATH; WAV files work without it. Python 3.13+ uses `audioop-lts` for
pydub compatibility, installed by the requirements file.

## Using the app

1. Choose single notes or chords and the strings you are playing.
2. Open a recording or press Record. Recording waits for a clear musical
   phrase, keeps the first pluck from the buffer, and shows provisional notes.
3. Review the tab or note graph. Scroll, zoom, or click the sheet to seek.
   The scroll slider stays below the sheet; Follow live returns to recording.
4. Adjust Target BPM. Under Advanced, apply rhythm settings, edit individual
   notes, or compare the original recording with the transcription.
5. Play the result or download MIDI, sheet music, or tablature. MusicXML files
   open in a notation editor; the app displays its own tab and note timeline.

Save recording locally writes to this project's `recordings/` folder. Imported
files keep their original format; microphone takes are WAV. Existing files
are not overwritten, and personal recordings are excluded from Git.

## Rhythm settings

Automatic fitting groups similar gaps and assigns consistent beat lengths.
Repeated notes can share their length instead of retaining uneven releases.
Clear pauses remain. Four-attack chord blocks can fit four quarter beats per
bar when repeated groups provide enough evidence.

A sixteenth-note grid allows sixteenth-note positions; it does not mean every
note is a sixteenth. For four attacks per beat, choose **Advanced → Intended
spacing → Even sixteenths → Apply timing settings**. Eighth and quarter spacing
are also available. Turn off consistent lengths to keep articulation differences.

Undo restores the previous timing operation. Disabling automatic timing
restores performed notes. Changing BPM changes playback speed, preserving beat
positions. The original audio is not time-stretched, so mixed playback is
unavailable after rhythm or tempo changes.

## Code

- `src/frontend/`: Electron window, microphone capture, sheet drawing, and controls.
- `src/backend/api.py`: Upload, transcription, editing, playback, and export routes.
- `src/backend/models.py`: Request validation.
- `src/backend/audio_processing/`: Attacks, pitch detection, tempo, and rhythm.
- `src/backend/sheet_music/`: Notation and string/fret assignment.
- `src/backend/playback/`: MIDI synthesis and audio mixing.
- `src/backend/editor/`: Note/track helpers and accompaniment generation.
- `tests/`: Synthetic audio, API, notation, and local recording regression tests.
- `tools/`: Desktop startup and recording diagnostics.

See [architecture](docs/architecture.md) for the data flow and
[interview preparation](docs/interview-guide.md) for a demo plan and technical explanations.

## Checks

```cmd
.venv\Scripts\python -m pytest tests
npm run test:recorder
.venv\Scripts\python -m black --check src tests tools backend_launcher.py
npm run check:frontend
```

Format Python with Black and frontend files with `npm run format:frontend`.
CI checks formatting, Python tests, JavaScript syntax, and recorder behavior.
The Node lockfile is committed so `npm ci` uses the same desktop dependencies.

Local reference tests use `smooth.wav` and `rough.wav` (32 single-note attacks
each) and `mitski.wav` (64 dyad attacks, 128 pitches). These files are not
published; reference tests skip if they are missing. Synthetic fixtures still
run on a clean checkout. These checks establish correctness on those cases,
not an accuracy percentage across arbitrary songs.

## Optional model and builds

The default detectors use librosa, NumPy, and SciPy. Basic Pitch is an optional
polyphonic engine under Advanced:

```cmd
.venv\Scripts\python -m pip install -r requirements-ml.txt
.venv\Scripts\python -m pip install --no-deps basic-pitch
```

The separate requirements avoid older Basic Pitch NumPy pins. Model packaging
can vary by Python version; the core app works without the model.

`build-all.bat` runs the PyInstaller backend and electron-builder Windows
installer builds. Installed packaging needs separate validation from running
the source checkout.

## Limits

- Best suited to isolated guitar. It does not separate a guitar from vocals or
  backing tracks. Dense chords and distortion need broader evaluation.
- Live notes are provisional. Full-take analysis after Stop has more context.
- Intent, BPM beat interpretation, and string choice can be ambiguous. Rhythm
  and string settings are user constraints, not guaranteed recovery of intent.
- Standard tuning and frets 0–24 are assumed. Several strings can play the same
  pitch; the selected strings constrain a playable fingering.
- Projects are held in memory and disappear when the audio service restarts.
- Triplet/swing grids are not implemented. The fallback synth approximates a
  plucked guitar; it does not reproduce the original performance's timbre.
- Accompaniment generation is retained in the backend, with its UI hidden.

MIT license. External libraries and models retain their own licenses.
