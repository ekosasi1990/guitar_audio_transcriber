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

1. Launch the app (`start.bat` or the installed `.exe` installer).
2. Import an MP3 / WAV file or record guitar directly with your microphone.
3. Click **Transcribe** to detect notes.
4. Review and edit detected notes in the multitrack editor.
5. Add accompaniment tracks if desired.
6. Export the result to MIDI or view sheet music / tablature.

## Building a Windows Installer

To create a single `.exe` installer that bundles both the Python backend and the Electron frontend:

```cmd
build-all.bat
```

This produces a `dist/Guitar Audio Transcriber Setup.exe` installer. The installer includes a `dist-backend/gat-backend/gat-backend.exe` which the frontend launches automatically on startup.

Because the backend includes audio / ML libraries, the installed app will be several hundred MB. The build excludes unused GUI toolkits (`tkinter`, `PyQt*`, `PySide*`, `wx`) to keep it as small as possible.

## License

MIT
