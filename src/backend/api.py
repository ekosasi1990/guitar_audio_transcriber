import os
import uuid
import shutil
import tempfile
import io
import math
import numpy as np
import librosa
import soundfile as sf
from copy import deepcopy
from datetime import datetime
from typing import Dict, Literal
from fastapi import FastAPI, File, HTTPException, UploadFile, Form, Query
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from .audio_processing.quantization import fit_rhythm, auto_fit_rhythm, group_events
from .audio_processing.tempo_estimation import estimate_note_tempo, repeated_pattern
from .audio_processing.playing_confirmation import confirm_playing

from .audio_processing import (
    load_audio,
    estimate_tempo,
    quantize_notes,
    export_midi,
)
from .editor import generate_accompaniment
from .sheet_music import notes_to_musicxml, notes_to_tab
from .sheet_music.fingering import tablature_events
from .audio_processing.transcription import transcribe_audio
from .models import (
    NoteEdit,
    AccompanimentRequest,
    RhythmFit,
    TimingSettings,
    TempoChange,
)
from .playback import render_synced_audio

app = FastAPI(title="Guitar Audio Transcriber API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

UPLOAD_DIR = tempfile.mkdtemp(prefix="gat_uploads_")
OUTPUT_DIR = os.path.join(UPLOAD_DIR, "exports")
os.makedirs(OUTPUT_DIR, exist_ok=True)

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RECORDINGS_DIR = os.path.join(REPO_ROOT, "recordings")

# In-memory project store
PROJECTS: Dict[str, dict] = {}


@app.post("/upload")
async def upload_audio(file: UploadFile = File(...)):
    project_id = str(uuid.uuid4())
    project_dir = os.path.join(UPLOAD_DIR, project_id)
    os.makedirs(project_dir, exist_ok=True)
    filename = os.path.basename(file.filename or "audio.wav")
    file_path = os.path.join(project_dir, filename)
    with open(file_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    y, sr = load_audio(file_path)
    PROJECTS[project_id] = {
        "id": project_id,
        "audio_path": file_path,
        "y": y,
        "sr": sr,
        "bpm": 120.0,
        "tracks": {},
        "accompaniment": None,
    }
    return {"project_id": project_id, "duration": len(y) / sr}


@app.post("/transcribe/{project_id}")
async def transcribe(
    project_id: str,
    quantize: bool = False,
    q_strength: float = Query(1.0, ge=0, le=1),
    mode: Literal["melody", "chords", "neural"] = "melody",
    noise_floor: float = Query(0.3, ge=0.1, le=0.6),
    trim: bool = False,
    tidy: bool = False,
    target_bpm: float | None = Query(None, ge=20, le=300),
    subdivisions: int = Query(4, ge=2, le=8),
    beats_per_measure: int = Query(4, ge=1, le=12),
    recognize_patterns: bool = True,
    string_set: Literal["all", "top", "bottom"] = "all",
):
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found")
    project = PROJECTS[project_id]
    if subdivisions not in (2, 4, 8):
        raise HTTPException(
            422, "Timing grid must be 2, 4, or 8 subdivisions per beat."
        )
    y, sr = project["y"], project["sr"]

    detected_bpm, _ = estimate_tempo(y, sr)
    flat_notes, engine = transcribe_audio(project, mode, noise_floor, string_set)
    project["string_set"] = string_set
    detected_bpm, pattern = estimate_note_tempo(
        flat_notes, detected_bpm, beats_per_measure
    )
    project["detected_bpm"] = detected_bpm
    project["detected_pattern"] = pattern
    bpm = target_bpm or detected_bpm
    offset = min((n["start"] for n in flat_notes), default=0) if trim else 0
    project["audio_offset"] = offset
    project["timing_changed"] = False
    flat_notes = [
        {**n, "start": max(0, n["start"] - offset), "end": n["end"] - offset}
        for n in flat_notes
    ]

    if quantize:
        flat_notes = quantize_notes(flat_notes, bpm, strength=q_strength)

    project["bpm"] = bpm
    project["tracks"]["Guitar"] = flat_notes
    project.pop("rhythm", None)
    project.pop("rhythm_undo", None)
    project["performed_notes"] = deepcopy(flat_notes)
    if tidy:
        _apply_automatic(
            project,
            TimingSettings(
                bpm=bpm,
                subdivisions=subdivisions,
                beats_per_measure=beats_per_measure,
                recognize_patterns=recognize_patterns,
            ),
        )

    return {
        "project_id": project_id,
        "bpm": bpm,
        "engine": engine,
        "tracks": project["tracks"],
        "rhythm": project.get("rhythm"),
        "can_undo_rhythm": "rhythm_undo" in project,
        "audio_offset": offset,
        "detected_bpm": detected_bpm,
        "tablature": tablature_events(project["tracks"].get("Guitar", []), string_set),
    }


@app.post("/live")
async def live_notes(
    file: UploadFile = File(...),
    mode: Literal["melody", "chords"] = "melody",
    noise_floor: float = Query(0.3, ge=0.1, le=0.6),
    string_set: Literal["all", "top", "bottom"] = "all",
    window_offset: float = Query(0, ge=0),
    playing_started: bool = False,
):
    """Analyze a bounded PCM preview without creating projects or saving files."""
    data = await file.read(2_000_001)
    if len(data) > 2_000_000:
        raise HTTPException(413, "Live preview must be at most six seconds.")
    try:
        y, rate = sf.read(io.BytesIO(data), dtype="float32")
    except Exception as exc:
        raise HTTPException(422, "Live preview requires WAV audio.") from exc
    if len(y) / rate > 6:
        raise HTTPException(413, "Live preview must be at most six seconds.")
    if y.ndim > 1:
        y = y.mean(axis=1)
    if rate != 22050:
        y = librosa.resample(y, orig_sr=rate, target_sr=22050)
    notes, engine = transcribe_audio(
        {"y": y, "sr": 22050}, mode, noise_floor, string_set
    )
    # The left edge can imitate a fresh attack; the right edge lacks enough
    # sustain to resolve a chord. Later overlapping snapshots analyze both.
    analysis_start = 0.25 if window_offset > 0 else 0
    analysis_end = max(0, len(y) / 22050 - (0.28 if mode == "chords" else 0.17))
    notes = [n for n in notes if analysis_start <= n["start"] <= analysis_end]
    confirmation = confirm_playing(y, 22050, notes)
    if not playing_started and confirmation["playing_confirmed"]:
        notes = [n for n in notes if n["start"] >= confirmation["music_start"] - 0.03]
    elif not playing_started:
        notes = []
    return {
        "notes": notes,
        "engine": engine,
        "tablature": tablature_events(notes, string_set),
        "analysis_start": analysis_start,
        "analysis_end": analysis_end,
        **confirmation,
    }


@app.get("/tempo/{project_id}")
async def detected_tempo(project_id: str):
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found")
    project = PROJECTS[project_id]
    if "detected_bpm" in project:
        return {
            "bpm": project["detected_bpm"],
            "pattern": project.get("detected_pattern"),
        }
    bpm, _ = estimate_tempo(project["y"], project["sr"])
    bpm, pattern = estimate_note_tempo(project.get("performed_notes", []), bpm)
    return {"bpm": bpm, "pattern": pattern}


def _apply_automatic(project, settings):
    project["rhythm_undo"] = deepcopy(
        {k: project.get(k) for k in ("tracks", "bpm", "rhythm")}
    )
    source = project.get("performed_notes", project["tracks"].get("Guitar", []))
    notes = (
        auto_fit_rhythm(
            source,
            settings.bpm,
            settings.subdivisions,
            settings.beats_per_measure,
            settings.recognize_patterns,
        )
        if settings.automatic
        else deepcopy(source)
    )
    project["tracks"]["Guitar"] = notes
    project["bpm"] = settings.bpm
    project["rhythm"] = (
        {
            "mode": "auto",
            "beats_per_measure": settings.beats_per_measure,
            "subdivisions": settings.subdivisions,
            "pattern": (
                repeated_pattern(source, settings.beats_per_measure)
                if settings.recognize_patterns
                else None
            ),
            "measures": max(
                1,
                math.ceil(
                    max(
                        (
                            n["start"] * settings.bpm / 60
                            + n.get("beat_duration", 0.25)
                            for n in notes
                        ),
                        default=0,
                    )
                    / settings.beats_per_measure
                ),
            ),
        }
        if settings.automatic
        else None
    )


@app.post("/timing/{project_id}")
async def timing(project_id: str, settings: TimingSettings):
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found")
    _apply_automatic(PROJECTS[project_id], settings)
    return await get_tracks(project_id)


@app.post("/tempo/{project_id}")
async def change_tempo(project_id: str, settings: TempoChange):
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found")
    project = PROJECTS[project_id]
    ratio = project["bpm"] / settings.bpm
    for notes in project["tracks"].values():
        for n in notes:
            n["start"] *= ratio
            n["end"] *= ratio
    for n in project.get("performed_notes", []):
        n["start"] *= ratio
        n["end"] *= ratio
    project["bpm"] = settings.bpm
    project["timing_changed"] = not math.isclose(ratio, 1.0) or project.get(
        "timing_changed", False
    )
    project.pop("rhythm_undo", None)
    return await get_tracks(project_id)


@app.post("/recordings")
async def save_recording(file: UploadFile = File(...), name: str = Form("")):
    """Save a recorded take into the repo's recordings/ dir for tuning."""
    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    extension = os.path.splitext(file.filename or "take.wav")[1].lower()
    if extension not in (".wav", ".mp3"):
        raise HTTPException(422, "Choose WAV or MP3 audio to save.")
    base = (
        os.path.basename(name)
        if name
        else datetime.now().strftime("take-%Y%m%d-%H%M%S-%f")
    )
    if not base.lower().endswith(extension):
        base += extension
    path = os.path.join(RECORDINGS_DIR, base)
    if os.path.exists(path):
        stem, extension = os.path.splitext(base)
        base = f"{stem}-{uuid.uuid4().hex[:8]}{extension}"
        path = os.path.join(RECORDINGS_DIR, base)
    with open(path, "xb") as f:
        shutil.copyfileobj(file.file, f)
    return {"path": path, "filename": base}


@app.get("/tracks/{project_id}")
async def get_tracks(project_id: str):
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "bpm": PROJECTS[project_id]["bpm"],
        "tracks": PROJECTS[project_id]["tracks"],
        "rhythm": PROJECTS[project_id].get("rhythm"),
        "can_undo_rhythm": "rhythm_undo" in PROJECTS[project_id],
        "tablature": tablature_events(
            PROJECTS[project_id]["tracks"].get("Guitar", []),
            PROJECTS[project_id].get("string_set", "all"),
        ),
        "timing_changed": PROJECTS[project_id].get("timing_changed", False),
    }


@app.post("/rhythm/{project_id}")
async def apply_rhythm(project_id: str, settings: RhythmFit):
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found")
    project = PROJECTS[project_id]
    if set(project["tracks"]) != {"Guitar"}:
        raise HTTPException(422, "Fit the guitar rhythm before adding accompaniment.")
    try:
        notes = fit_rhythm(project["tracks"]["Guitar"], **settings.model_dump())
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    project["rhythm_undo"] = deepcopy(
        {k: project.get(k) for k in ("tracks", "bpm", "rhythm")}
    )
    project["tracks"]["Guitar"] = notes
    project["bpm"] = settings.bpm
    project["rhythm"] = settings.model_dump()
    return await get_tracks(project_id)


@app.post("/rhythm/{project_id}/undo")
async def undo_rhythm(project_id: str):
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found")
    project = PROJECTS[project_id]
    previous = project.pop("rhythm_undo", None)
    if previous is None:
        raise HTTPException(422, "No rhythm fit to undo.")
    project.update(previous)
    return await get_tracks(project_id)


@app.post("/edit/{project_id}")
async def edit_note(project_id: str, edit: NoteEdit):
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found")
    tracks = PROJECTS[project_id]["tracks"]
    if edit.track not in tracks:
        raise HTTPException(status_code=404, detail="Track not found")

    for n in tracks[edit.track]:
        if n["pitch"] == edit.old_pitch and abs(n["start"] - edit.old_start) < 0.001:
            n["pitch"] = edit.new_pitch
            n["start"] = edit.new_start
            n["end"] = edit.new_end
            n["velocity"] = edit.new_velocity
            n.pop("beat_duration", None)
            break
    PROJECTS[project_id].pop("rhythm_undo", None)
    PROJECTS[project_id]["performed_notes"] = deepcopy(tracks.get("Guitar", []))
    return {"status": "updated", "tracks": tracks}


@app.post("/accompaniment/{project_id}")
async def add_accompaniment(project_id: str, req: AccompanimentRequest):
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found")
    bpm = PROJECTS[project_id]["bpm"]
    duration = len(PROJECTS[project_id]["y"]) / PROJECTS[project_id]["sr"]
    accompaniment = generate_accompaniment(req.chords, bpm, duration)
    PROJECTS[project_id]["accompaniment"] = accompaniment
    PROJECTS[project_id]["tracks"].update(accompaniment)
    PROJECTS[project_id].pop("rhythm_undo", None)
    return {"status": "ok", "tracks": PROJECTS[project_id]["tracks"]}


@app.post("/export/{project_id}")
async def export_midi_endpoint(project_id: str, filename: str = "export.mid"):
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found")
    project = PROJECTS[project_id]
    safe_name = os.path.basename(filename)
    output_path = os.path.join(OUTPUT_DIR, f"{project_id}_{safe_name}")
    instruments = {"Guitar": 25}
    export_midi(project["tracks"], project["bpm"], instruments, output_path)
    return FileResponse(output_path, media_type="audio/midi", filename=safe_name)


@app.get("/sheet/{project_id}")
async def generate_sheet(
    project_id: str, format: str = "musicxml", download: bool = False
):
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found")
    project = PROJECTS[project_id]
    if format == "musicxml":
        path = os.path.join(OUTPUT_DIR, f"{project_id}_sheet.xml")
        notes_to_musicxml(
            project["tracks"],
            project["bpm"],
            path,
            (project.get("rhythm") or {}).get("beats_per_measure", 4),
        )
    else:
        path = os.path.join(OUTPUT_DIR, f"{project_id}_tab.xml")
        guitar_notes = project["tracks"].get("Guitar", [])
        notes_to_tab(
            guitar_notes,
            project["bpm"],
            path,
            (project.get("rhythm") or {}).get("beats_per_measure", 4),
            project.get("string_set", "all"),
        )
    if download:
        return FileResponse(
            path,
            media_type="application/vnd.recordare.musicxml+xml",
            filename="tablature.musicxml" if format == "tab" else "sheet.musicxml",
        )
    return {"sheet_path": path}


@app.post("/playback/{project_id}")
async def generate_playback(project_id: str, mix_ratio: float = Query(1.0, ge=0, le=1)):
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found")
    project = PROJECTS[project_id]
    if (project.get("rhythm") or project.get("timing_changed")) and mix_ratio < 1:
        raise HTTPException(
            422,
            "Use notes-only playback after fitting rhythm; the original audio keeps its performed timing.",
        )
    midi_path = os.path.join(OUTPUT_DIR, f"{project_id}_playback.mid")
    instruments = {"Guitar": 25}
    export_midi(project["tracks"], project["bpm"], instruments, midi_path)
    output_path = os.path.join(OUTPUT_DIR, f"{project_id}_mixed.wav")
    render_synced_audio(
        project["audio_path"],
        midi_path,
        output_path,
        mix_ratio,
        original_offset=project.get("audio_offset", 0),
    )
    return FileResponse(output_path, media_type="audio/wav", filename="playback.wav")
