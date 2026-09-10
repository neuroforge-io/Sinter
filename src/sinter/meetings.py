"""Transcript-preserving draft minutes with human-confirmed speaker labels."""
from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass

from .evidence import literal, text


@dataclass(frozen=True)
class Segment:
    id: str
    speaker: str
    text: str
    start: float | None = None
    end: float | None = None


def _seconds(value: str) -> float:
    parts = value.replace(",", ".").split(":")
    if len(parts) not in {2, 3}:
        raise ValueError("Invalid transcript timestamp.")
    numbers = [float(part) for part in parts]
    if any(not math.isfinite(number) or number < 0 for number in numbers) or numbers[-1] >= 60 or numbers[-2] >= 60:
        raise ValueError("Invalid transcript timestamp.")
    return numbers[-1] + numbers[-2] * 60 + (numbers[0] * 3600 if len(numbers) == 3 else 0)


def parse_transcript(value: str) -> list[Segment]:
    text(value, "Transcript", 200000, True)
    rows = []
    if value.strip().startswith(("[", "{")):
        data = json.loads(value)
        rows = data.get("segments") if isinstance(data, dict) else data
        if not isinstance(rows, list):
            raise ValueError("Transcript JSON needs a segments array.")
    elif "-->" in value:
        for block in re.split(r"\n\s*\n", value.replace("\r\n", "\n")):
            lines = block.splitlines()
            timing = next((index for index, line in enumerate(lines) if "-->" in line), None)
            if timing is None:
                continue
            left, right = lines[timing].split("-->", 1)
            if not right.strip():
                raise ValueError("Missing transcript end time.")
            start, end = _seconds(left.strip()), _seconds(right.strip().split()[0])
            content = " ".join(lines[timing + 1:]).strip()
            voice = re.match(r"<v\s+([^>]+)>(.*?)(?:</v>)?$", content)
            rows.append({"start": start, "end": end, "speaker": voice[1] if voice else "Unidentified",
                         "text": voice[2] if voice else content})
    else:
        for line in value.splitlines():
            if not line.strip():
                continue
            match = re.match(r"^([^:\n]{1,60}):\s+(.+)$", line)
            rows.append({"speaker": match[1] if match else "Unidentified", "text": match[2] if match else line})
    if not rows or len(rows) > 3000:
        raise ValueError("Provide between 1 and 3,000 transcript segments.")
    result = []
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError("Each transcript segment needs text.")
        content = text(row.get("text", ""), "Segment text", 20000, True)
        speaker = text(row.get("speaker") or "Unidentified", "Speaker label", 100, True)
        start, end = row.get("start"), row.get("end")
        if start is not None or end is not None:
            if any(type(number) not in {int, float} or not math.isfinite(number) for number in (start, end)):
                raise ValueError("Segment times must be finite numbers in seconds.")
            if not 0 <= start <= end:
                raise ValueError("A segment must end at or after its start.")
        result.append(Segment(f"T{index + 1:04d}", speaker, content, start, end))
    return result


def minutes(title: str, transcript: str, speaker_map: dict | None = None,
            corrections: list[dict] | None = None) -> dict:
    text(title, "Meeting title", 200, True)
    segments = parse_transcript(transcript)
    speaker_map = {} if speaker_map is None else speaker_map
    corrections = [] if corrections is None else corrections
    if not isinstance(speaker_map, dict) or not isinstance(corrections, list) or len(corrections) > len(segments):
        raise ValueError("Speaker mappings and corrections have invalid formats.")
    speakers = {segment.speaker for segment in segments}
    if set(speaker_map) - speakers:
        raise ValueError("A speaker mapping refers to an unknown transcript label.")
    for key, name in speaker_map.items():
        text(name, "Confirmed speaker name", 100, True)
        if key == "Unidentified":
            raise ValueError("Unidentified turns cannot all be assigned to one person. Label individual turns first.")
    corrected, audit = {}, []
    by_id = {segment.id: segment for segment in segments}
    for change in corrections:
        if not isinstance(change, dict) or not isinstance(change.get("segment_id"), str) or change["segment_id"] not in by_id:
            raise ValueError("A correction refers to an unknown segment.")
        original = by_id[change["segment_id"]]
        if change.get("original") != original.text:
            raise ValueError("The original transcript changed. Review the correction again.")
        replacement = text(change.get("replacement", ""), "Corrected text", 20000, True)
        reason = text(change.get("reason", ""), "Correction reason", 500, True)
        if original.id in corrected:
            raise ValueError("Only one reviewed correction per segment is allowed.")
        corrected[original.id] = replacement
        audit.append({"segment_id": original.id, "original": original.text,
                      "replacement": replacement, "reason": reason, "author": "human reviewer"})
    lines = [f"# {literal(title)}", "DRAFT MINUTES - NOT APPROVED",
             "Speaker labels and transcription are not proof of identity. Names below are human-supplied mappings. "
             "Check against the recording; attendance, resolutions, votes and deadlines are not inferred.",
             "## Items for the chair to review"]
    candidates = []
    for segment in segments:
        content = corrected.get(segment.id, segment.text)
        if re.search(r"\b(action|will|agreed|motion|resolved|seconded|vote|carried|decision)\b", content, re.I):
            candidates.append({"segment_id": segment.id, "quote": content, "status": "needs_review"})
            lines.append(f"- [{segment.id}] {literal(content)} (candidate only; confirm the outcome)")
    if not candidates:
        lines.append("No explicit action/decision keywords were found. Review the transcript; this is not proof none occurred.")
    lines.append("## Transcript record")
    for segment in segments:
        name = speaker_map.get(segment.speaker, segment.speaker + " (identity unconfirmed)")
        timing = f"{segment.start:g}-{segment.end:g} seconds" if segment.start is not None else "time not supplied"
        lines.append(f"### [{segment.id}] {literal(name)} | {timing}\n\n{literal(corrected.get(segment.id, segment.text))}")
    lines.append("## Review checklist\n\n- Verify identities and ambiguous words against the recording.\n"
                 "- Confirm attendance, motions, voting outcomes, action owners and due dates.\n"
                 "- Obtain chair/committee approval before issuing official minutes.")
    if audit:
        lines.append("## Human correction history")
        for change in audit:
            lines.append(f"[{change['segment_id']}] Original: {literal(change['original'])}\n\n"
                         f"Replacement: {literal(change['replacement'])}\n\nReason: {literal(change['reason'])}")
    return {"markdown": "\n\n".join(lines), "segments": [asdict(segment) for segment in segments],
            "speaker_map": speaker_map, "corrections": audit, "candidates": candidates}
