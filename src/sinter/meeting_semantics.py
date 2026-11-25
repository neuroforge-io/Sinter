"""Typed organizational event composition over reviewed meeting passages.

This is the semantic layer between a transcript and draft minutes. It recovers
clause-level events (motion, amendment, acceptance, responsibility, deadline,
budget, attendance) and composes them across passages. A caller may inject an
ERAIS semantic interpreter with the same event contract; the deterministic
interpreter here is the local fallback and test fixture, not a second lexical
authority.

The layer deliberately never upgrades a stated agreement into formal approval.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re
from typing import Callable, Iterable

SCHEMA = "sinter.meeting-semantics.v1"
EVENT_SCHEMA = "sinter.organizational-event.v1"

AMOUNT = re.compile(
    r"(?P<currency>[$£€])?\s?(?P<value>\d[\d,]*(?:\.\d+)?)"
    r"(?:\s?(?P<unit>dollars?|euros?|pounds?|cents?))?", re.I)
DATE = re.compile(
    r"\b(?:\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}(?:/\d{2,4})?|"
    r"(?:next\s+)?(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)|"
    r"january|february|march|april|may|june|july|august|september|october|"
    r"november|december)\b", re.I)
MOTION = re.compile(
    r"\b(?:motion|proposal)\b|\b(?:we|i)\s+(?:should|propose|move|suggest|recommend)\b|"
    r"\b(?:allocate|spend|commit|budget)\b", re.I)
AMEND = re.compile(
    r"\b(?:amend(?:ment|ed)?|make\s+(?:that|it)|change\s+(?:that|it)|"
    r"instead|rather|can\s+we\s+(?:make|do)\s+that)\b", re.I)
ACCEPT = re.compile(
    r"\b(?:yes|agreed?|agreement|that\s+works?|works\s+for\s+me|seconded?|"
    r"accepted?|approved?|carried|adopt(?:ed)?|let'?s\s+do\s+that)\b", re.I)
WITHDRAW = re.compile(r"\b(?:withdraw|withdrawn|withdraws)\b", re.I)
DISCUSSION = re.compile(
    r"\b(?:discuss(?:ed|ion)?|consider(?:ed)?|defer(?:red)?|tabled?|"
    r"reviewed?|noted?)\b", re.I)
RESPONSIBILITY = re.compile(
    r"(?P<actor>I|we|Speaker\s+[A-Z]|[A-Z][a-z]+)"
    r"(?:\s+(?:will|shall|is\s+to|are\s+to)|'ll)\s+"
    r"(?P<action>.+)$", re.I)
ASSIGN = re.compile(
    r"\b(?:assign(?:ed)?|ask(?:ed)?)\s+(?P<actor>[A-Z][a-z]+|Speaker\s+[A-Z])\s+"
    r"(?:to\s+)?(?P<action>.+)$", re.I)
ATTENDANCE = re.compile(
    r"\b(?:absent|attendance|apolog(?:y|ies|ised|ized)|quorum)\b", re.I)
OUTCOME = re.compile(
    r"\b(?P<value>carried|lost|approved|accepted|rejected|withdrawn|pending)\b",
    re.I)
PROCUREMENT = re.compile(
    r"\b(?:purchase|purchasing|order|ordering|buy|buying|procure|procurement|"
    r"acquire|arrange|organize)\b", re.I)


@dataclass(frozen=True)
class Passage:
    passage_id: str
    speaker: str
    text: str
    start: float | None = None
    end: float | None = None


def _clean(value: str) -> str:
    return " ".join(value.split()).strip(" ,;.")


def clauses(text: str) -> list[str]:
    """Split on sentence and contrast boundaries without inventing clauses."""
    parts = re.split(r"(?<=[.!?])\s+|;\s*|\s+(?:but|however)\s+", text,
                     flags=re.I)
    return [part.strip() for part in parts if part.strip()]


def _amount(text: str) -> dict | None:
    for match in AMOUNT.finditer(text):
        value = match.group("value").replace(",", "")
        try:
            number = float(value)
        except ValueError:
            continue
        if number <= 0:
            continue
        currency = match.group("currency") or ""
        unit = (match.group("unit") or "").lower()
        if currency == "$" or unit.startswith("dollar"):
            currency = "USD"
        elif currency == "£" or unit.startswith("pound"):
            currency = "GBP"
        elif currency == "€" or unit.startswith("euro"):
            currency = "EUR"
        else:
            currency = currency or ""
        return {"raw": match.group(0).strip(), "value": number,
                "currency": currency}
    return None


def _date(text: str) -> str | None:
    match = DATE.search(text)
    return _clean(match.group(0)) if match else None


def _object(text: str, amount: dict | None) -> str:
    body = text
    if amount:
        body = body.replace(amount["raw"], " ")
    body = re.sub(
        r"\b(?:we|i|the|a|an|should|propose|move|suggest|recommend|motion|"
        r"proposal|to|for|of|spend|allocate|commit|budget|approved?|"
        r"carried|lost|accepted?|rejected?|amend(?:ment|ed)?|make|that|it|"
        r"change|instead|rather|can)\b", " ", body, flags=re.I)
    return _clean(body)


def interpret_passage(passage: Passage) -> list[dict]:
    """Return clause-level events using explicit roles and source evidence.

    The function is deterministic and conservative. It does not claim formal
    approval, attendance or identity; those remain review obligations.
    """
    events: list[dict] = []
    for clause in clauses(passage.text):
        amount = _amount(clause)
        due = _date(clause)
        upper = clause.strip()
        event_type = None
        actor = passage.speaker
        action = ""
        object_text = _object(clause, amount)
        outcome = ""
        if WITHDRAW.search(clause):
            event_type = "motion"
            outcome = "withdrawn"
        elif AMEND.search(clause) and amount:
            event_type = "amendment"
        elif MOTION.search(clause):
            event_type = "motion"
            match = OUTCOME.search(clause)
            if match:
                outcome = match.group("value").lower()
                if re.search(
                        r"\bnot\s+" + re.escape(match.group("value")),
                        clause, re.I):
                    outcome = "not_" + outcome
        elif amount and re.search(
                r"\b(?:approved?|allocated?|spent|committed?|budget)\b",
                clause, re.I):
            event_type = "budget"
        elif RESPONSIBILITY.search(clause):
            event_type = "responsibility"
            match = RESPONSIBILITY.search(clause)
            actor = passage.speaker if match.group("actor").lower() in {
                "i", "we"} else match.group("actor")
            action = _clean(match.group("action"))
        elif ASSIGN.search(clause):
            event_type = "responsibility"
            match = ASSIGN.search(clause)
            actor = match.group("actor")
            action = _clean(match.group("action"))
        if (event_type is None and ACCEPT.search(upper) and len(upper) <= 120
                and not re.search(
                    r"\b(?:not|no|never|without|didn'?t)\b", upper, re.I)):
            event_type = "acceptance"
        if event_type is None and DISCUSSION.search(clause):
            event_type = "discussion"
        if event_type is None and ATTENDANCE.search(clause):
            event_type = "attendance"
        if event_type is None and clause.rstrip().endswith("?"):
            event_type = "question"
        if event_type is None:
            continue
        event = {
            "schema": EVENT_SCHEMA,
            "event_type": event_type,
            "source_passage_id": passage.passage_id,
            "source_speaker": passage.speaker,
            "source_start": passage.start,
            "source_end": passage.end,
            "evidence": clause,
            "actor": actor if event_type in {
                "responsibility", "motion", "amendment"} else None,
            "action": action or None,
            "object": object_text or None,
            "amount": amount,
            "due_date": due,
            "outcome": outcome or None,
            "confidence": 0.8 if event_type in {"motion", "amendment"} else 0.7,
            "assertion_status": "stated",
            "confirmation_status": "unconfirmed",
        }
        if event_type == "acceptance":
            event["acceptance_status"] = "stated_agreement"
        events.append(event)
    return events


def _event_id(passage_index: int, event: dict, ordinal: int) -> str:
    return f"E{passage_index:04d}:{event['event_type']}:{ordinal:02d}"


def _same_procurement(left: dict, right: dict) -> bool:
    text = " ".join(filter(None, [left.get("action"), left.get("object"),
                                  left.get("evidence")]))
    motion = " ".join(filter(None, [right.get("object"),
                                    right.get("evidence")]))
    return bool(PROCUREMENT.search(text)) and bool(
        PROCUREMENT.search(motion) or re.search(
            r"\b(?:equipment|repair|purchase|supplies|budget|fund)\b", motion,
            re.I))


def compose(passages: Iterable[Passage],
            interpreter: Callable[[Passage], list[dict]] | None = None) -> dict:
    """Compose clause events into motions, amendments and responsibilities."""
    interpret = interpreter or interpret_passage
    events: list[dict] = []
    motions: list[dict] = []
    active = None
    last_responsibility = None
    for passage_index, passage in enumerate(passages, 1):
        parsed = interpret(passage)
        if not isinstance(parsed, list) or not all(
                isinstance(item, dict) for item in parsed):
            raise ValueError("The semantic interpreter returned invalid events.")
        counts: dict[str, int] = {}
        for item in parsed:
            event = dict(item)
            event.setdefault("schema", EVENT_SCHEMA)
            event.setdefault("source_passage_id", passage.passage_id)
            event.setdefault("source_speaker", passage.speaker)
            event.setdefault("source_start", passage.start)
            event.setdefault("source_end", passage.end)
            event.setdefault("assertion_status", "stated")
            event.setdefault("confirmation_status", "unconfirmed")
            kind = str(event.get("event_type") or "")
            if not kind:
                continue
            counts[kind] = counts.get(kind, 0) + 1
            event["event_id"] = _event_id(passage_index, event, counts[kind])
            event["related_event_ids"] = []
            if kind == "motion":
                event["chain_id"] = event["event_id"]
                event["status"] = "proposed"
                event["amount_history"] = (
                    [{"event_id": event["event_id"],
                      "amount": event.get("amount"), "kind": "proposal"}]
                    if event.get("amount") else [])
                event["amendments"] = []
                event["acceptance"] = None
                event["responsibility_ids"] = []
                if event.get("outcome") in {"carried", "approved", "accepted"}:
                    event["acceptance"] = "stated_outcome"
                motions.append(event)
                active = event
            elif kind == "amendment" and active is not None:
                event["motion_id"] = active["event_id"]
                event["related_event_ids"] = [active["event_id"]]
                active["amendments"].append(event["event_id"])
                active["related_event_ids"].append(event["event_id"])
                active["amount_history"].append({
                    "event_id": event["event_id"],
                    "amount": event.get("amount"), "kind": "amendment"})
                if event.get("amount"):
                    active["current_amount"] = event["amount"]
            elif kind == "acceptance" and active is not None:
                event["motion_id"] = active["event_id"]
                event["related_event_ids"] = [active["event_id"]]
                if active.get("acceptance") is None:
                    active["acceptance"] = "stated_agreement"
                active["acceptance_event_id"] = event["event_id"]
                active["related_event_ids"].append(event["event_id"])
            elif kind == "responsibility":
                event["responsibility_status"] = "stated"
                last_responsibility = event
                if active is not None and _same_procurement(event, active):
                    event["motion_id"] = active["event_id"]
                    event["related_event_ids"].append(active["event_id"])
                    active["responsibility_ids"].append(event["event_id"])
                    active["related_event_ids"].append(event["event_id"])
                    event["_link_motion"] = True
            elif kind == "budget" and active is not None:
                event["motion_id"] = active["event_id"]
                event["related_event_ids"].append(active["event_id"])
                active["related_event_ids"].append(event["event_id"])
                if event.get("amount"):
                    active["related_amount"] = event["amount"]
            elif kind == "due_date" and last_responsibility is not None:
                event["related_event_ids"].append(
                    last_responsibility["event_id"])
                last_responsibility["related_event_ids"].append(
                    event["event_id"])
                last_responsibility["due_date"] = event.get("due_date")
            if (kind == "responsibility" and event.get("due_date")
                    and last_responsibility is event):
                # The clause carries both the action and its deadline.
                event["related_event_ids"].append(event["event_id"])
            events.append(event)
            if kind in {"motion", "amendment"} and event.get("amount"):
                counts["budget"] = counts.get("budget", 0) + 1
                budget = {
                    "schema": EVENT_SCHEMA,
                    "event_type": "budget",
                    "event_id": _event_id(
                        passage_index, {"event_type": "budget"},
                        counts["budget"]),
                    "source_passage_id": event["source_passage_id"],
                    "source_speaker": event["source_speaker"],
                    "source_start": event["source_start"],
                    "source_end": event["source_end"],
                    "evidence": event.get("evidence"),
                    "actor": event.get("actor"),
                    "action": None,
                    "object": event.get("object"),
                    "amount": event.get("amount"),
                    "due_date": None,
                    "outcome": None,
                    "confidence": event.get("confidence"),
                    "assertion_status": "stated",
                    "confirmation_status": "unconfirmed",
                    "related_event_ids": [event["event_id"]],
                }
                if active is not None:
                    budget["motion_id"] = active["event_id"]
                    budget["related_event_ids"].append(active["event_id"])
                    active["related_event_ids"].append(budget["event_id"])
                events.append(budget)
    return {"schema": SCHEMA, "events": events, "motions": motions}


ACTION_VERBS = {
    "organize", "organise", "purchase", "order", "buy", "procure", "arrange",
    "obtain", "prepare", "send", "submit", "approve", "reject", "cancel",
    "withdraw", "review", "sign", "deliver", "install", "collect", "pay",
}


OBJECT_STOP = {"the", "a", "an", "some", "this", "that", "these", "those"}


def _object_signature(value: object) -> str:
    if not isinstance(value, str):
        return ""
    words = [word for word in re.findall(r"[a-z]+", value.lower())
             if word not in OBJECT_STOP]
    return words[-1] if words else ""


def _action_signature(action: object) -> tuple[str, ...]:
    if not isinstance(action, str):
        return ()
    words = set(re.findall(r"[a-z]+", action.lower()))
    return tuple(sorted(words & ACTION_VERBS))


def _index(events: Iterable[dict]) -> dict[str, dict]:
    return {str(event.get("event_id")): event for event in events
            if event.get("event_id")}


def compare(old: dict, new: dict) -> dict:
    """Compare two composed graphs and return changed event identities."""
    old_events = _index(old.get("events") or ())
    new_events = _index(new.get("events") or ())
    fields = ("event_type", "actor", "action", "object", "amount", "due_date",
              "outcome", "acceptance_status")
    changed: dict[str, dict] = {}
    removed: list[str] = []
    for identifier, before in old_events.items():
        after = new_events.get(identifier)
        if after is None:
            removed.append(identifier)
            continue
        differences = {}
        for field in fields:
            if field == "action":
                if _action_signature(before.get(field)) == _action_signature(
                        after.get(field)):
                    continue
            if field == "object":
                if _object_signature(before.get(field)) == _object_signature(
                        after.get(field)):
                    continue
            if before.get(field) != after.get(field):
                differences[field] = {
                    "original": before.get(field),
                    "corrected": after.get(field)}
        if differences:
            changed[identifier] = differences
    for identifier in new_events:
        if identifier not in old_events:
            changed[identifier] = {"event_type": {
                "original": None, "corrected": new_events[identifier].get(
                    "event_type")}}
    old_motions = _index(old.get("motions") or ())
    new_motions = _index(new.get("motions") or ())
    for identifier, before in old_motions.items():
        after = new_motions.get(identifier)
        if after is None:
            continue
        for field in ("acceptance", "amount_history", "responsibility_ids"):
            if before.get(field) != after.get(field):
                changed.setdefault(identifier, {})[field] = {
                    "original": before.get(field),
                    "corrected": after.get(field)}
    related: dict[str, list[str]] = {}
    for motion in list(old_motions.values()) + list(new_motions.values()):
        related[motion["event_id"]] = list(
            motion.get("related_event_ids") or ())
    return {"changed": changed, "removed": removed, "related": related}


def _claim_id(event: dict) -> str:
    return "C" + hashlib.sha256(str(event.get("event_id")).encode()).hexdigest()[:8]


def claims(composed: dict, revision: dict | None = None) -> list[dict]:
    """Convert events to reviewable claims with evidentiary status."""
    revision = revision or {"changed": {}, "removed": [], "related": {}}
    changed = revision.get("changed") or {}
    related = revision.get("related") or {}
    affected = set(changed) | set(revision.get("removed") or ())
    claims = []
    events_by_id = {
        str(event.get("event_id")): event
        for event in composed.get("events") or ()
    }
    for event in composed.get("events") or ():
        kind = event.get("event_type")
        if kind not in {
                "motion", "amendment", "acceptance", "responsibility", "budget",
                "due_date", "attendance", "question", "discussion"}:
            continue
        claim_type = {
            "motion": "motion", "amendment": "motion_amendment",
            "acceptance": "decision", "responsibility": "action",
            "budget": "financial", "due_date": "due_date",
            "attendance": "attendance", "question": "question",
            "discussion": "discussion",
        }[kind]
        event_id = event.get("event_id")
        stale = event_id in affected
        record = {
            "claim_id": _claim_id(event),
            "claim_type": claim_type,
            "event_type": kind,
            "event_id": event_id,
            "asserted_content": event.get("evidence", ""),
            "source_passage_id": event.get("source_passage_id"),
            "source_speaker": event.get("source_speaker"),
            "source_start": event.get("source_start"),
            "source_end": event.get("source_end"),
            "assertion_status": "stated",
            "evidence_status": "transcript_only",
            "confirmation_status": "unconfirmed",
            "claim_status": "stale" if stale else "current",
            "reinterpretation_required": stale,
            "semantic_event": {
                "event_type": kind,
                "actor": event.get("actor"),
                "action": event.get("action"),
                "object": event.get("object"),
                "amount": event.get("amount"),
                "due_date": event.get("due_date"),
                "outcome": event.get("outcome"),
                "acceptance_status": event.get("acceptance_status"),
            },
            "related_event_ids": list(event.get("related_event_ids") or ()),
        }
        motion = next(
            (item for item in composed.get("motions") or ()
             if item.get("event_id") == event.get("motion_id")), None)
        if motion is not None:
            record["motion_id"] = motion.get("event_id")
            record["related_event_ids"] = sorted(set(
                record["related_event_ids"] + list(
                    motion.get("related_event_ids") or ())))
        if event_id in changed:
            record["semantic_revision"] = changed[event_id]
            record["claim_status"] = "stale"
            record["reinterpretation_required"] = True
        record["related_event_ids"] = sorted(set(
            record.get("related_event_ids") or ()))
        if kind == "motion":
            linked_types = {
                event_id: str((events_by_id.get(event_id) or {}).get(
                    "event_type") or "")
                for event_id in record["related_event_ids"]
            }
            if any(
                    event_id in affected
                    and linked_types.get(event_id) in {
                        "amendment", "budget", "acceptance"}
                    for event_id in record["related_event_ids"]):
                record["claim_status"] = "stale"
                record["reinterpretation_required"] = True
            if revision.get("removed") and record["related_event_ids"]:
                record["claim_status"] = "stale"
                record["reinterpretation_required"] = True
        claims.append(record)
        if kind == "responsibility" and event.get("due_date"):
            due_record = dict(record)
            due_record.update({
                "claim_id": _claim_id(event) + "D",
                "claim_type": "due_date",
                "event_type": "due_date",
                "asserted_content": event.get("evidence", ""),
                "semantic_event": {
                    "event_type": "due_date",
                    "due_date": event.get("due_date"),
                    "actor": event.get("actor"),
                    "action": event.get("action"),
                },
            })
            if stale or (event_id in affected):
                due_record["claim_status"] = "stale"
                due_record["reinterpretation_required"] = True
            claims.append(due_record)
    return claims


def analyze(passages: Iterable[Passage],
            interpreter: Callable[[Passage], list[dict]] | None = None,
            revision_source: Iterable[Passage] | None = None) -> dict:
    """Compose current semantics and propagate revisions from source text."""
    current = compose(passages, interpreter)
    revision = {"changed": {}, "removed": [], "related": {}}
    if revision_source is not None:
        revision = compare(compose(revision_source, interpreter), current)
    return {
        "schema": SCHEMA,
        "events": current["events"],
        "motions": current["motions"],
        "claims": claims(current, revision),
        "revision": revision,
    }


__all__ = [
    "Passage", "SCHEMA", "EVENT_SCHEMA", "analyze", "claims", "clauses",
    "compare", "compose", "interpret_passage",
]
