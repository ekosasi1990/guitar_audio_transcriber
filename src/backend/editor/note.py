class Note:
    def __init__(self, pitch: int, start: float, end: float, velocity: int = 80):
        self.pitch = pitch
        self.start = start
        self.end = end
        self.velocity = velocity

    def to_dict(self):
        return {
            "pitch": self.pitch,
            "start": self.start,
            "end": self.end,
            "velocity": self.velocity,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(d["pitch"], d["start"], d["end"], d.get("velocity", 80))
