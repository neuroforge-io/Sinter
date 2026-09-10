"""Install optional speech into this checkout's isolated environment, never system Python.

Run explicitly: python3 setup_speech.py (Windows: py setup_speech.py).
No model is downloaded by this helper. The application asks separately on first use.
"""
from __future__ import annotations

import os
import subprocess
import sys
import venv
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def main():
    if sys.version_info < (3, 10):
        raise SystemExit("Sinter needs Python 3.10 or newer. Install it, then run this helper again.")
    print("Sinter local speech setup\nThis downloads optional Python packages into .venv. No recording is uploaded and no model is downloaded.")
    answer = input("Continue? [y/N] ").strip().lower()
    if answer not in {"y", "yes"}:
        print("Nothing installed.")
        return
    directory = ROOT / ".venv"
    python = directory / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    try:
        if not python.exists():
            venv.EnvBuilder(with_pip=True).create(directory)
        subprocess.run([str(python), "-m", "pip", "install", ".[speech]"], cwd=ROOT, check=True)
        subprocess.run([str(python), "-c", "from faster_whisper import WhisperModel; print('Speech engine import OK')"], cwd=ROOT, check=True)
    except (OSError, subprocess.CalledProcessError) as exc:
        raise SystemExit("Setup did not finish. Check the error above, your connection and free disk space. See docs/TRANSCRIPTION.md; the core app is unchanged.") from exc
    print("Ready. Stop Sinter and start it again with your usual launcher. It will use .venv automatically.\nThen open Meeting minutes > Start with an audio recording.")


if __name__ == "__main__":
    main()
