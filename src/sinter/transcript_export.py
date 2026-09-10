"""Plain-text subtitle exports. JSON remains the lossless, reviewable master."""
from __future__ import annotations

import html
import json

from .meetings import parse_transcript


def _stamp(seconds: float, separator: str) -> str:
    value = round(seconds * 1000)
    hours, value = divmod(value, 3600000)
    minutes, value = divmod(value, 60000)
    seconds, millis = divmod(value, 1000)
    return f"{hours:02d}:{minutes:02d}:{seconds:02d}{separator}{millis:03d}"


def export_transcript(transcript: dict, format: str = "json") -> str:
    if not isinstance(format, str) or format not in {"json", "srt", "vtt", "txt"}:
        raise ValueError("Choose json, txt, srt or vtt.")
    if format == "json":
        return json.dumps(transcript, ensure_ascii=False, indent=2, allow_nan=False)
    segments = parse_transcript(json.dumps(transcript, ensure_ascii=False, allow_nan=False))
    blocks = ["WEBVTT\n\nNOTE Draft transcription; review against the recording.\n"] if format == "vtt" else []
    for index, row in enumerate(segments, 1):
        # Collapse cue delimiters and escape markup so transcript text stays inert.
        content = " ".join(row.text.split())
        speaker = " ".join(row.speaker.split())
        if format == "txt":
            blocks.append(f"{speaker}: {content}")
            continue
        if row.start is None or row.end is None or row.end <= row.start:
            raise ValueError("Subtitle export requires non-empty time ranges for every segment.")
        separator = "." if format == "vtt" else ","
        content = html.escape(f"{speaker}: {content}").replace("--&gt;", "- -&gt;")
        blocks.append(f"{index}\n{_stamp(row.start, separator)} --> {_stamp(row.end, separator)}\n{content}\n")
    return "\n".join(blocks)
