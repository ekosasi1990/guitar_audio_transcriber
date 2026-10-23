"""Start the local audio service and desktop app from any working directory."""

import argparse
import json
from pathlib import Path
import subprocess
import sys
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
ELECTRON = ROOT / "node_modules" / "electron" / "dist" / "electron.exe"
API_URL = "http://127.0.0.1:8000/openapi.json"


def backend_ready():
    try:
        with urllib.request.urlopen(API_URL, timeout=2) as response:
            data = json.load(response)
    except urllib.error.URLError:
        return False
    except (json.JSONDecodeError, TimeoutError) as exc:
        raise RuntimeError(
            "The service on port 8000 is not responding as expected. Close it and try again."
        ) from exc
    if data.get("info", {}).get("title") != "Guitar Audio Transcriber API":
        raise RuntimeError(
            "Another application is using port 8000. Close it before starting the transcriber."
        )
    return True


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Check startup without opening a window"
    )
    args = parser.parse_args()
    if not ELECTRON.is_file():
        raise RuntimeError(
            "Desktop dependencies are missing. Run npm install in the project folder first."
        )
    import importlib.util

    if importlib.util.find_spec("uvicorn") is None:
        raise RuntimeError(
            "Python dependencies are missing. Install requirements.txt with this Python first."
        )
    ready = backend_ready()
    if args.check:
        print("Desktop dependencies found.")
        print(
            "Audio service is already running."
            if ready
            else "Audio service will be started on launch."
        )
        return
    if not ready:
        print("Starting the audio service...")
        logs = ROOT / "output"
        logs.mkdir(exist_ok=True)
        log_path = logs / "startup-backend.log"
        with log_path.open("ab") as log:
            process = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "src.backend.api:app",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    "8000",
                ],
                cwd=ROOT,
                stdout=log,
                stderr=log,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
        deadline = time.monotonic() + 30
        try:
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(
                        f"The audio service could not start. Details are in {log_path}"
                    )
                if backend_ready():
                    break
                time.sleep(0.3)
            else:
                raise RuntimeError(
                    f"The audio service took too long to start. Details are in {log_path}"
                )
        except Exception:
            if process.poll() is None:
                process.terminate()
            raise
    else:
        print("Using the running audio service.")
    print("Opening Guitar Audio Transcriber...")
    subprocess.Popen(
        [str(ELECTRON), str(ROOT / "src" / "frontend" / "main.js")], cwd=ROOT
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Unable to start: {exc}", file=sys.stderr)
        sys.exit(1)
