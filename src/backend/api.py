import logging
import os
import uuid
import shutil
import tempfile
from datetime import datetime
from typing import Dict, List
from fastapi import FastAPI, File, HTTPException, UploadFile, Form
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .audio_processing import (
    load_audio,
    detect_onsets,
    detect_pitches,
    estimate_tempo,
    quantize_notes,
    export_midi,
)
from .editor import generate_accompaniment
from .sheet_music import notes_to_musicxml, notes_to_tab
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

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
RECORDINGS_DIR = os.path.join(REPO_ROOT, "recordings")

# In-memory project store
PROJECTS: Dict[str, dict] = {}


class NoteEdit(BaseModel):
    track: str
    old_pitch: int
    old_start: float
    new_pitch: int
    new_start: float
    new_end: float
    new_velocity: int


class AccompanimentRequest(BaseModel):
    chords: List[List]  # [ [beat, "C"], ... ]


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


def _run_transcription(project):
    """Return (flat_notes, engine_name) using Basic Pitch when available."""
    try:
        from .audio_processing.neural_transcription import transcribe_neural

        return (transcribe_neural(project["audio_path"],
                                  y=project["y"], sr=project["sr"]),
                "basic-pitch")
    except Exception as exc:
        logging.warning("Basic Pitch unavailable (%s); using DSP pipeline", exc)

    y, sr = project["y"], project["sr"]
    onsets, offsets = detect_onsets(y, sr)
    raw_notes = detect_pitches(y, sr, onsets, offsets)
    flat_notes = []
    for group in raw_notes:
        for pitch in group["pitches"]:
            flat_notes.append({
                "pitch": pitch,
                "start": group["start"],
                "end": group["end"],
                "velocity": 80,
            })
    return flat_notes, "dsp"


@app.post("/transcribe/{project_id}")
async def transcribe(project_id: str, quantize: bool = True, q_strength: float = 1.0):
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found")
    project = PROJECTS[project_id]
    y, sr = project["y"], project["sr"]

    bpm, _ = estimate_tempo(y, sr)
    flat_notes, engine = _run_transcription(project)

    if quantize:
        flat_notes = quantize_notes(flat_notes, bpm, strength=q_strength)

    project["bpm"] = bpm
    project["tracks"]["Guitar"] = flat_notes

    return {
        "project_id": project_id,
        "bpm": bpm,
        "engine": engine,
        "tracks": {"Guitar": flat_notes},
    }


@app.post("/recordings")
async def save_recording(file: UploadFile = File(...), name: str = Form("")):
    """Save a recorded take into the repo's recordings/ dir for tuning."""
    os.makedirs(RECORDINGS_DIR, exist_ok=True)
    base = os.path.basename(name) if name else datetime.now().strftime("take-%Y%m%d-%H%M%S")
    if not base.lower().endswith(".wav"):
        base += ".wav"
    path = os.path.join(RECORDINGS_DIR, base)
    with open(path, "wb") as f:
        shutil.copyfileobj(file.file, f)
    return {"path": path, "filename": base}


@app.get("/tracks/{project_id}")
async def get_tracks(project_id: str):
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found")
    return {
        "bpm": PROJECTS[project_id]["bpm"],
        "tracks": PROJECTS[project_id]["tracks"],
    }


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
            break
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
async def generate_sheet(project_id: str, format: str = "musicxml"):
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found")
    project = PROJECTS[project_id]
    if format == "musicxml":
        path = os.path.join(OUTPUT_DIR, f"{project_id}_sheet.xml")
        notes_to_musicxml(project["tracks"], project["bpm"], path)
    else:
        path = os.path.join(OUTPUT_DIR, f"{project_id}_tab.xml")
        guitar_notes = project["tracks"].get("Guitar", [])
        notes_to_tab(guitar_notes, project["bpm"], path)
    return {"sheet_path": path}


@app.post("/playback/{project_id}")
async def generate_playback(project_id: str, mix_ratio: float = 0.4):
    if project_id not in PROJECTS:
        raise HTTPException(status_code=404, detail="Project not found")
    project = PROJECTS[project_id]
    midi_path = os.path.join(OUTPUT_DIR, f"{project_id}_playback.mid")
    instruments = {"Guitar": 25}
    export_midi(project["tracks"], project["bpm"], instruments, midi_path)
    output_path = os.path.join(OUTPUT_DIR, f"{project_id}_mixed.wav")
    render_synced_audio(project["audio_path"], midi_path, output_path, mix_ratio)
    return FileResponse(output_path, media_type="audio/wav", filename="playback.wav")
