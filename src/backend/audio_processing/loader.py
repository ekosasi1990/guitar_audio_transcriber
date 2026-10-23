import os
import tempfile
import librosa
import soundfile as sf


def load_audio(file_path: str, sr: int = 22050, mono: bool = True):
    """Load an MP3 or WAV file and return audio signal and sample rate."""
    ext = os.path.splitext(file_path)[1].lower()
    if ext == ".mp3":
        try:
            from pydub import AudioSegment
        except ImportError as exc:
            raise RuntimeError(
                "MP3 support requires pydub (and, on Python 3.13+, audioop-lts)"
            ) from exc
        audio = AudioSegment.from_mp3(file_path)
        if mono:
            audio = audio.set_channels(1)
        audio = audio.set_frame_rate(sr)
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            audio.export(tmp.name, format="wav")
            wav_path = tmp.name
        y, _ = librosa.load(wav_path, sr=sr, mono=mono)
        os.unlink(wav_path)
    else:
        y, _ = librosa.load(file_path, sr=sr, mono=mono)
    return y, sr


def write_wav(y, sr, path):
    sf.write(path, y, sr)
