"""Request validation for editing, rhythm, and playback settings."""

from typing import List, Literal
from pydantic import BaseModel, Field


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


class RhythmFit(BaseModel):
    bpm: float = Field(120, ge=20, le=300, allow_inf_nan=False)
    measures: int = Field(4, ge=1, le=128)
    beats_per_measure: int = Field(4, ge=1, le=12)
    notes_per_measure: int = Field(8, ge=1, le=64)
    pattern: List[float] | None = None
    articulation: Literal["preserve", "staccato", "connected"] = "preserve"


class TimingSettings(BaseModel):
    bpm: float = Field(120, ge=20, le=300, allow_inf_nan=False)
    automatic: bool = True
    subdivisions: Literal[2, 4, 8] = 4
    beats_per_measure: int = Field(4, ge=1, le=12)
    recognize_patterns: bool = True
    intended_spacing: Literal["auto", "sixteenth", "eighth", "quarter"] = "auto"
    consistent_lengths: bool = True


class TempoChange(BaseModel):
    bpm: float = Field(120, ge=20, le=300, allow_inf_nan=False)
