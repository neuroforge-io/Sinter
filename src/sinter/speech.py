"""Optional local ASR with reviewable timings and explicit channel separation.

No proprietary inference code or weights are bundled. Channel labels describe
recording tracks, never a verified identity. Do not confuse them with diarization.
"""
from __future__ import annotations

import base64
import hashlib
import importlib.util
import math
import os
import re
import tempfile
import threading
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

MODEL_NAMES = {"tiny", "base", "small", "tiny.en", "base.en", "small.en"}
MAX_UPLOAD = 25 * 1024 * 1024
_LOCK = threading.Lock()
_CACHE: tuple[str, object] | None = None


def capabilities() -> dict:
    """Fast, local-only discovery; importing native engines is deferred to use."""
    available = importlib.util.find_spec("faster_whisper") is not None
    return {"available": available, "speaker_diarization": False,
            "channel_separation": True, "identity_verification": False,
            "models": sorted(MODEL_NAMES), "max_upload_bytes": MAX_UPLOAD,
            "notice": ("Local speech package found. First use also needs a cached model or download permission."
                       if available else "Install the optional speech package, then restart Sinter. Transcript import works without it.")}


def _number(value, name: str, minimum: float = 0) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or value < minimum:
        raise ValueError(f"The speech engine returned invalid {name}.")
    return round(float(value), 3)


def _segment(segment, speaker: str, duration: float) -> dict:
    start, end = _number(segment.start, "start time"), _number(segment.end, "end time")
    if end < start or end > duration + 1:
        raise ValueError("The speech engine returned out-of-range timings. Try a different model.")
    flags = []
    if segment.avg_logprob < -1 or segment.no_speech_prob > .6:
        flags.append("Uncertain recognition: listen again before using this passage.")
    if getattr(segment, "compression_ratio", 0) > 2.4:
        flags.append("Possible repetition: check against the recording.")
    words = []
    for word in getattr(segment, "words", None) or []:
        a, b = _number(word.start, "word time"), _number(word.end, "word time")
        probability = _number(word.probability, "word probability")
        if b < a or a < start - .1 or b > end + .1 or probability > 1:
            raise ValueError("The speech engine returned inconsistent word timings.")
        words.append({"start": a, "end": b, "word": str(word.word), "probability": probability})
    if any(word["probability"] < .5 for word in words):
        flags.append("Some words have low model confidence; this is not an accuracy score.")
    return {"start": start, "end": end, "speaker": speaker, "text": segment.text.strip(),
            "review_flags": flags, "words": words}


def _channel_inputs(path: Path):
    """Separate real stereo tracks only; do not duplicate mono into two speakers."""
    import av
    from faster_whisper.audio import decode_audio

    try:
        with av.open(str(path)) as recording:
            if not recording.streams.audio or recording.streams.audio[0].codec_context.channels != 2:
                raise ValueError("Separate-channel mode requires a true two-channel recording. Use mixed audio for a room microphone.")
        left, right = decode_audio(str(path), split_stereo=True)
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError("The recording could not be decoded. Try exporting a WAV or FLAC file.") from exc
    return [(left, "CHANNEL_1"), (right, "CHANNEL_2")]


def transcribe(path: Path, model: str = "base", consent: bool = False,
               allow_download: bool = False, progress=lambda message: None,
               *, language: str = "auto", split_channels: bool = False) -> dict:
    global _CACHE
    if consent is not True:
        raise ValueError("Confirm you have permission to process this recording before transcribing.")
    if not isinstance(model, str) or model not in MODEL_NAMES:
        raise ValueError("Choose tiny, base or small, optionally with .en for English-only recordings.")
    if not isinstance(language, str) or (language != "auto" and not re.fullmatch("[a-z]{2,3}", language)):
        raise ValueError("Choose automatic detection or a supported language code, such as en.")
    if model.endswith(".en") and language not in {"auto", "en"}:
        raise ValueError("An English-only model cannot transcribe another language. Select a multilingual model.")
    if type(split_channels) is not bool or type(allow_download) is not bool:
        raise ValueError("Channel separation and download permission must be true or false.")
    path = Path(path)
    if not path.is_file() or not 0 < path.stat().st_size <= 500 * 1024 * 1024:
        raise ValueError("Choose a non-empty recording smaller than 500 MB.")
    try:
        from faster_whisper import WhisperModel
    except (ImportError, OSError) as exc:
        raise ValueError('Local speech could not load. Run python setup_speech.py from the Sinter folder, then restart. Check the transcription guide for native-library errors.') from exc
    if not _LOCK.acquire(blocking=False):
        raise ValueError("Another recording is being transcribed. Finish it before starting another.")
    try:
        progress("Loading the local model; a first download can take a while. Cancellation takes effect after loading.")
        if _CACHE is None or _CACHE[0] != model:
            _CACHE = None  # Release the old model before allocating a replacement.
            try:
                backend = WhisperModel(model, device="cpu", compute_type="int8",
                                       cpu_threads=min(4, os.cpu_count() or 1),
                                       local_files_only=not allow_download)
            except Exception as exc:
                raise ValueError("The speech model could not be loaded. Allow its first download, check disk space and connection, or use a smaller model.") from exc
            _CACHE = (model, backend)
        selected_language = "en" if model.endswith(".en") else None if language == "auto" else language
        supported = getattr(_CACHE[1], "supported_languages", None)
        if supported and selected_language and selected_language not in supported:
            raise ValueError("This speech model does not support the selected language.")
        progress("Reading recording tracks locally")
        tracks = _channel_inputs(path) if split_channels else [(str(path), "Unidentified")]
        output, languages, duration, characters = [], [], 0.0, 0
        for audio, speaker in tracks:
            progress(f"Transcribing {speaker}; timings remain estimates")
            try:
                segments, info = _CACHE[1].transcribe(audio, beam_size=5, language=selected_language,
                    vad_filter=True, vad_parameters={"min_silence_duration_ms": 500, "speech_pad_ms": 300},
                    condition_on_previous_text=False, word_timestamps=True, hallucination_silence_threshold=2)
                track_duration = _number(info.duration, "recording duration")
                if track_duration > 4 * 3600:
                    raise ValueError("Split recordings longer than four hours into smaller sessions.")
                duration = max(duration, track_duration)
                languages.append(info.language)
                for segment in segments:
                    if not segment.text.strip():
                        continue
                    row = _segment(segment, speaker, track_duration)
                    progress(f"Transcribing {speaker}: {int(row['end'])} of {int(track_duration)} seconds")
                    output.append(row)
                    characters += len(segment.text)
                    if len(output) > 3000 or characters > 200000:
                        raise ValueError("The transcript exceeds the workbench limit. Split the recording into smaller sessions.")
            except (RuntimeError, OSError) as exc:
                raise ValueError("The recording could not be processed. Check the file, memory and speech installation; try a smaller model or a WAV export.") from exc
        output.sort(key=lambda row: (row["start"], row["speaker"]))
        for index, row in enumerate(output):
            row["id"] = f"T{index + 1:04d}"
        progress("Preparing transcript and review information")
        digest = hashlib.sha256()
        with path.open("rb") as recording:
            for block in iter(lambda: recording.read(1024 * 1024), b""):
                digest.update(block)
        try:
            engine_version = version("faster-whisper")
        except PackageNotFoundError:
            engine_version = "unknown"
        warnings = ["Check names, amounts, negation and unclear words against the recording. Confidence is not proof of correctness.",
                    "Channel labels identify recording tracks, not people. Confirm every name manually." if split_channels else
                    "Unidentified segments are not evidence that there was only one speaker."]
        if not output:
            warnings.insert(0, "No speech was detected. Check the file, microphone level and selected tracks; do not invent missing words.")
        return {"schema_version": 1, "segments": output, "language": languages[0] if languages else "unknown",
                "languages": languages, "duration": duration, "model": model, "audio_sha256": digest.hexdigest(),
                "engine": "optional local faster-whisper", "engine_version": engine_version,
                "speaker_diarization": False, "channel_separation": split_channels,
                "review_count": sum(bool(row["review_flags"]) for row in output),
                "status": "draft" if output else "no_speech", "warnings": warnings}
    finally:
        _LOCK.release()


def transcribe_upload(payload: dict, progress=lambda message: None) -> dict:
    if not isinstance(payload, dict) or payload.get("consent") is not True:
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
                          payload.get("allow_download", False), progress,
                          language=payload.get("language", "auto"),
                          split_channels=payload.get("split_channels", False))
