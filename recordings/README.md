# Local recordings

Saved microphone takes and imported recordings go here. WAV and MP3 files are
ignored by Git so personal recordings do not get pushed with the source code.

The local regression tests use `smooth.wav`, `rough.wav`, and `mitski.wav` when
available. They skip those checks if the files are absent; synthetic audio
tests still run on a clean checkout.
