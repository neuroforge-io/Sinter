"""Optional local speech adapter, separate from the zero-dependency core.

faster-whisper transcribes; it does NOT provide speaker diarization or identity.
Import separated transcripts and confirm names manually for multi-speaker work.
"""
from __future__ import annotations

import base64
import importlib.util
import tempfile
import threading
from pathlib import Path

MODEL_NAMES = {"tiny", "base", "small"}
MAX_UPLOAD = 25 * 1024 * 1024
_LOCK = threading.Lock()
_CACHE: tuple[str, object] | None = None


def capabilities() -> dict:
    return {"available": importlib.util.find_spec("faster_whisper") is not None,
            "speaker_diarization": False, "identity_verification": False,
            "notice": "Optional local speech recognition. Imported speaker labels and names still need human confirmation."}


def transcribe(path: Path, model: str = "base", consent: bool = False,
               allow_download: bool = False, progress=lambda message: None) -> dict:
    global _CACHE
    if consent is not True:
        raise ValueError("Confirm you have permission to process this recording before transcribing.")
    if not isinstance(model, str) or model not in MODEL_NAMES:
        raise ValueError("Choose the tiny, base or small local speech model.")
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= 500 * 1024 * 1024:
        raise ValueError("Choose a non-empty recording smaller than 500 MB.")
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise ValueError('Local speech is not installed. From the Sinter folder run: python -m pip install ".[speech]"') from exc
    if not _LOCK.acquire(blocking=False):
        raise ValueError("Another recording is being transcribed. Finish it before starting another.")
    try:
        progress("Loading the optional local speech model")
        if _CACHE is None or _CACHE[0] != model:
            try:
                backend = WhisperModel(model, device="cpu", compute_type="int8", cpu_threads=4,
                                       local_files_only=not allow_download)
            except Exception as exc:
                raise ValueError("The speech model could not be loaded. For first use, explicitly allow its model download.") from exc
            _CACHE = (model, backend)
        progress("Transcribing locally; speaker identities remain unconfirmed")
        segments, info = _CACHE[1].transcribe(str(path), beam_size=5, vad_filter=True,
                                             condition_on_previous_text=False, word_timestamps=True)
        if info.duration > 4 * 3600:
            raise ValueError("Split recordings longer than four hours into smaller sessions.")
        output, characters = [], 0
        for segment in segments:
            progress(f"Transcribing locally: {int(segment.end)} seconds processed")
            flags = ["Check this segment against the recording"] if segment.avg_logprob < -1 or segment.no_speech_prob > 0.6 else []
            output.append({"start": segment.start, "end": segment.end, "speaker": "Unidentified",
                           "text": segment.text, "review_flags": flags})
            characters += len(segment.text)
            if len(output) > 3000 or characters > 200000:
                raise ValueError("The transcript exceeds the workbench limit. Split the recording into smaller sessions.")
        if not output:
            raise ValueError("No speech was detected. Check the recording and audio level.")
        return {"segments": output, "language": info.language, "duration": info.duration,
                "engine": "optional local faster-whisper", "speaker_diarization": False,
                "warnings": ["Transcription can omit or invent words. Review against the original recording.",
                             "Unidentified segments are not evidence that there was only one speaker."]}
    finally:
        _LOCK.release()


def transcribe_upload(payload: dict, progress=lambda message: None) -> dict:
    if payload.get("consent") is not True:
        raise ValueError("Recording permission must be confirmed.")
    encoded = payload.get("audio", "")
    if not isinstance(encoded, str) or len(encoded) > ((MAX_UPLOAD + 2) // 3) * 4:
        raise ValueError("The browser recording limit is 25 MB. Use the CLI for larger recordings.")
    suffix = str(payload.get("filename", "audio.wav")).rsplit(".", 1)[-1].lower()
    if suffix not in {"wav", "mp3", "m4a", "ogg", "webm", "flac", "mp4"}:
        raise ValueError("Choose WAV, MP3, M4A, OGG, WebM, FLAC or MP4 audio.")
    try:
        data = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise ValueError("The recording upload is invalid. Select the file again.") from exc
    if not 0 < len(data) <= MAX_UPLOAD:
        raise ValueError("Choose a non-empty recording smaller than 25 MB.")
    with tempfile.TemporaryDirectory(prefix="sinter-audio-") as directory:
        path = Path(directory) / ("recording." + suffix)
        path.write_bytes(data)
        return transcribe(path, payload.get("model", "base"), True,
                          payload.get("allow_download") is True, progress)
