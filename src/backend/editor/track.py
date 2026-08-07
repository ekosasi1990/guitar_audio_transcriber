from .note import Note


class Track:
    def __init__(self, name: str, instrument: int = 0):
        self.name = name
        self.instrument = instrument
        self.notes = []

    def add_note(self, note: Note):
        self.notes.append(note)

    def remove_note(self, pitch, start):
        self.notes = [n for n in self.notes if not (n.pitch == pitch and abs(n.start - start) < 0.001)]

    def update_note(self, old_pitch, old_start, **kwargs):
        for n in self.notes:
            if n.pitch == old_pitch and abs(n.start - old_start) < 0.001:
                for k, v in kwargs.items():
                    if hasattr(n, k):
                        setattr(n, k, v)
                return n
        return None

    def to_dict(self):
        return {
            "name": self.name,
            "instrument": self.instrument,
            "notes": [n.to_dict() for n in self.notes],
        }

    @classmethod
    def from_dict(cls, d):
        t = cls(d["name"], d.get("instrument", 0))
        for n in d.get("notes", []):
            t.add_note(Note.from_dict(n))
        return t
