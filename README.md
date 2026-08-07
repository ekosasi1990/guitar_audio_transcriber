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

This installs Python and Node dependencies.

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

And in another Command Prompt:

```cmd
npm start
```

## Usage

1. Launch the backend server (`uvicorn src.backend.api:app`).
2. Launch the Electron app (`npm start` from `src/frontend`).
3. Import an MP3 or WAV guitar recording.
4. Review the detected notes in the multitrack editor.
5. Edit pitch, timing, duration, or instrument assignments.
6. Add accompaniment tracks if desired.
7. Export the result to MIDI or view sheet music / tablature.

## License

MIT
