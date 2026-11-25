"""Transcript-preserving draft minutes with human-confirmed speaker labels."""
from __future__ import annotations

import hashlib
import json
import math
import os
import re
from dataclasses import asdict, dataclass, field

from .evidence import literal, text
from .meeting_semantics import Passage, analyze
from .experience_feedback import from_environment as experience_from_environment
from .organizational_interpreter import from_environment


@dataclass(frozen=True)
class Segment:
    id: str
    speaker: str
    text: str
    start: float | None = None
    end: float | None = None
    review_flags: list[str] = field(default_factory=list)


def _seconds(value: str) -> float:
    parts = value.replace(",", ".").split(":")
    if len(parts) not in {2, 3}:
        raise ValueError("Invalid transcript timestamp.")
    numbers = [float(part) for part in parts]
    if any(not math.isfinite(number) or number < 0 for number in numbers) or numbers[-1] >= 60 or numbers[-2] >= 60:
        raise ValueError("Invalid transcript timestamp.")
    return numbers[-1] + numbers[-2] * 60 + (numbers[0] * 3600 if len(numbers) == 3 else 0)


def parse_transcript(value: str) -> list[Segment]:
    text(value, "Transcript", 1000000, True)
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
        flags = row.get("review_flags", [])
        if not isinstance(flags, list) or len(flags) > 10 or any(not isinstance(flag, str) or len(flag) > 500 for flag in flags):
            raise ValueError("Segment review flags must be short text messages.")
        result.append(Segment(f"T{index + 1:04d}", speaker, content, start, end, flags))
    if sum(len(row.text) for row in result) > 200000:
        raise ValueError("Transcript text exceeds 200,000 characters. Split the meeting into parts.")
    return result


# ---------------------------------------------------------------- claims
#
# A transcript establishes what a participant *said*. It does not establish
# that the asserted state of the world is true. These records keep that
# distinction explicit: every claim is "stated" evidence from one passage,
# unconfirmed unless a human reviewer confirms it, and stale when a reviewed
# correction changes its outcome or amount.

CLAIM_RULES = (
    ("motion", r"\b(motion|moved|move that|proposal)\b"),
    ("vote", r"\b(vote|voted|unanimous|abstain|abstained|carried|lost)\b"),
    ("decision", r"\b(agreed|resolved|approved|accepted|adopted|decided|rejected)\b"),
    ("action", r"\b(will|shall|is to|are to|action item|action:)\b"),
    ("attendance", r"\b(absent|present|apolog(?:y|ies|ised|ized)|attendance|quorum)\b"),
    ("financial", r"(?:[$\u00a3\u20ac]\s?\d[\d,]*(?:\.\d+)?|\b\d[\d,]*(?:\.\d+)?\s?(?:dollars|euros|pounds|cents)\b)"),
    ("due_date", r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?|(?:next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|january|february|march|april|may|june|july|august|september|october|november|december)\b"),
    ("question", r"\?\s*$"),
)

POLARITY = {
    "not", "no", "never", "none", "carried", "lost", "approved", "rejected",
    "accepted", "withdrawn", "pending", "unanimous",
}
AMOUNT = re.compile(
    r"(?:[$\u00a3\u20ac]\s?\d[\d,]*(?:\.\d+)?|"
    r"\b\d[\d,]*(?:\.\d+)?\s?(?:dollars|euros|pounds|cents)\b)",
    re.I)


def _amounts(value: str) -> tuple[str, ...]:
    return tuple(sorted(match.group(0).replace(" ", "").lower()
                        for match in AMOUNT.finditer(value)))


def _polarity(value: str) -> tuple[str, ...]:
    return tuple(sorted(word for word in POLARITY
                        if re.search(rf"\b{word}\b", value, re.I)))


def claims(segments: list[Segment], corrections: list[dict],
           corrected: dict[str, str]) -> list[dict]:
    """Classify candidate claims while preserving their evidentiary status.

    Only explicit keywords and amounts create a candidate. Nothing here infers
    that a motion passed, that an amount was approved, or that an absent person
    attended. A later reviewed correction that changes outcome words or values
    marks the dependent claim stale instead of silently rewriting it.
    """
    changes = {}
    for change in corrections:
        changes[change["segment_id"]] = change
    result = []
    for segment in segments:
        content = corrected.get(segment.id, segment.text)
        types = [name for name, pattern in CLAIM_RULES
                 if re.search(pattern, content, re.I)]
        if not types:
            continue
        for kind in types:
            identifier = f"C{len(result) + 1:04d}"
            record = {
                "claim_id": identifier,
                "claim_type": kind,
                "asserted_content": content,
                "source_passage_id": segment.id,
                "source_speaker": segment.speaker,
                "source_start": segment.start,
                "source_end": segment.end,
                "assertion_status": "stated",
                "evidence_status": "transcript_only",
                "confirmation_status": "unconfirmed",
                "claim_status": "current",
                "reinterpretation_required": False,
            }
            change = changes.get(segment.id)
            if change is not None:
                before = change["original"]
                after = corrected.get(segment.id, segment.text)
                amounts_changed = _amounts(before) != _amounts(after)
                polarity_changed = _polarity(before) != _polarity(after)
                record["transcript_revision"] = {
                    "original": before,
                    "replacement": after,
                    "reason": change.get("reason", ""),
                }
                if amounts_changed or polarity_changed:
                    record["claim_status"] = "stale"
                    record["reinterpretation_required"] = True
            result.append(record)
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
    semantic_passages = [
        Passage(segment.id, segment.speaker,
                corrected.get(segment.id, segment.text),
                segment.start, segment.end)
        for segment in segments
    ]
    source_passages = [
        Passage(segment.id, segment.speaker, segment.text,
                segment.start, segment.end)
        for segment in segments
    ]
    interpreter = from_environment()
    semantics = analyze(
        semantic_passages,
        interpreter=interpreter,
        revision_source=source_passages if corrections else None)
    experience_receipts = []
    feedback = experience_from_environment()
    if feedback is not None and audit:
        scope_id = "meeting:" + hashlib.sha256(
            title.encode("utf-8")).hexdigest()[:16]
        for change in audit:
            experience_receipts.append(feedback.record(
                change, scope_id=scope_id,
                source_revision=os.environ.get(
                    "SINTER_SOURCE_REVISION", "unknown")))
    claim_records = semantics["claims"]
    changes_by_id = {change["segment_id"]: change for change in corrections}
    for record in claim_records:
        change = changes_by_id.get(record.get("source_passage_id"))
        if change is not None:
            record["transcript_revision"] = {
                "original": change["original"],
                "replacement": corrected.get(change["segment_id"],
                                             change["original"]),
                "reason": change.get("reason", ""),
            }
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
    if claim_records:
        if semantics["events"]:
            lines.append("## Organizational event composition")
            lines.append(
                "Events are composed across passages. A motion remains a "
                "proposal; an amendment is linked to its motion; agreement is "
                "recorded as stated agreement, not formal approval.")
            for event in semantics["events"]:
                kind = event.get("event_type")
                amount = event.get("amount") or {}
                bits = [f"{kind.upper()} [{event.get('event_id')}]"]
                if event.get("actor"):
                    bits.append(f"actor={event['actor']}")
                if event.get("action"):
                    bits.append(f"action={literal(event['action'])}")
                if event.get("object"):
                    bits.append(f"object={literal(event['object'])}")
                if amount:
                    bits.append(f"amount={amount.get('raw')}")
                if event.get("due_date"):
                    bits.append(f"due={literal(event['due_date'])}")
                if event.get("outcome"):
                    bits.append(f"outcome={event['outcome']}")
                if event.get("motion_id"):
                    bits.append(f"motion={event['motion_id']}")
                lines.append("- " + "; ".join(bits))
            for motion in semantics["motions"]:
                history = motion.get("amount_history") or []
                if len(history) > 1:
                    lines.append(
                        f"- MOTION CHAIN [{motion.get('event_id')}]: "
                        + " -> ".join(
                            str(row.get("amount", {}).get("raw"))
                            for row in history if row.get("amount"))
                        + f"; acceptance={motion.get('acceptance') or 'unconfirmed'}")
        lines.append("## Candidate meeting claims")
        lines.append(
            "Each row records what a participant stated. It is not evidence "
            "that the asserted state, outcome or amount is true. Confirm "
            "against the recording and the chair before issuing minutes.")
        for record in claim_records:
            state = record["claim_status"]
            note = (" (transcript corrected; reinterpret before relying on it)"
                    if state == "stale" else "")
            lines.append(
                f"- [{record['claim_id']}] {record['claim_type']}: "
                f"\"{literal(record['asserted_content'])}\" "
                f"[{record['source_passage_id']}, {record['source_speaker']}] "
                f"- stated only, unconfirmed{note}")
        stale = [record for record in claim_records
                 if record["reinterpretation_required"]]
        if stale:
            lines.append("## Claims invalidated by transcript revision")
            for record in stale:
                revision = record.get("transcript_revision")
                if revision is not None:
                    lines.append(
                        f"- [{record['claim_id']}] Original: "
                        f"\"{literal(revision['original'])}\" -> Corrected: "
                        f"\"{literal(revision['replacement'])}\" "
                        f"({literal(revision['reason'])})")
                else:
                    changed = sorted((record.get("semantic_revision") or {}))
                    lines.append(
                        f"- [{record['claim_id']}] Depends on a changed "
                        f"event: {', '.join(changed) or 'related event'}")
    flagged = [segment for segment in segments if segment.review_flags]
    if flagged:
        lines.append("## Passages requiring an audio check")
        for segment in flagged:
            lines.append(f"- [{segment.id}] " + "; ".join(literal(flag) for flag in segment.review_flags))
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
    return {"markdown": "\n\n".join(lines),
            "segments": [asdict(segment) for segment in segments],
            "speaker_map": speaker_map, "corrections": audit,
            "candidates": candidates, "claims": claim_records,
            "organizational_events": semantics["events"],
            "motions": semantics["motions"],
            "semantic_revision": semantics["revision"],
            "organizational_interpreter": (
                "erais" if interpreter is not None else "deterministic"),
            "experience_receipts": experience_receipts}
