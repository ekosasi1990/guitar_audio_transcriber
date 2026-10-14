import sys
import os

# Ensure src is on the import path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))


def test_import_backend():
    from backend import api  # noqa: F401


def test_note_model():
    from backend.editor.note import Note

    n = Note(60, 0.0, 1.0, 80)
    d = n.to_dict()
    assert d["pitch"] == 60
    assert d["start"] == 0.0
    assert d["end"] == 1.0
