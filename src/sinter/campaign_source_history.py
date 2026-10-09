"""Bounded, literal source snapshots kept apart from current campaign evidence."""

from __future__ import annotations

from collections.abc import Callable

from .evidence import literal

FIELD_LABELS = {
    "opportunity": "Previous route name",
    "rule": "Previous requirement",
    "status": "Previous user-entered assessment",
    "evidence": "Previous applicant evidence",
    "source_id": "Retained source ID",
    "source_url": "Previous source URL",
    "source_quote": "Previous source wording",
    "checked_at": "Previous check date (user-entered)",
    "kind": "Previous evidence type",
    "title": "Previous reference title",
    "url": "Previous source URL",
    "excerpt": "Previous source passage",
    "notes": "Previous reference note",
}
WORKSTREAM_LABELS = {
    "contributors_status": "contributor",
    "rights_status": "rights",
    "disclosure_status": "disclosure",
    "prior_art_status": "prior-art",
}


def validate_history(
    value: object,
    *,
    label: str,
    limit: int,
    record: Callable[[dict], dict],
    assessment: Callable[[dict, dict], dict] | None = None,
) -> list[dict]:
    """Admit exact non-recursive records; never fill them from today's register."""
    if not isinstance(value, list) or len(value) > limit:
        raise ValueError(f"{label} must contain at most {limit} historical snapshots.")
    result = []
    for entry in value:
        fields = {"state", "reason", "record"}
        if assessment is not None:
            fields.add("assessment")
        if not isinstance(entry, dict) or set(entry) - fields:
            raise ValueError(f"{label} contains unsupported fields.")
        if entry.get("state") != "historical" or entry.get("reason") not in {
            "replaced",
            "cleared",
        }:
            raise ValueError(
                f"{label} must be explicitly historical source replacements."
            )
        if not isinstance(entry.get("record"), dict):
            raise ValueError(f"{label} needs the previous source record.")
        snapshot = record(entry["record"])
        normalized = {
            "state": "historical",
            "reason": entry["reason"],
            "record": snapshot,
        }
        if "assessment" in entry:
            if not isinstance(entry["assessment"], dict):
                raise ValueError(f"{label} needs a historical assessment object.")
            normalized["assessment"] = assessment(entry["assessment"], snapshot)
        result.append(normalized)
    return result


def historical_lines(row: dict) -> list[str]:
    """Export every retained value with an explicit exclusion from current checks."""
    lines = []
    for index, entry in enumerate(row.get("source_history", []), 1):
        lines.extend(
            [
                f"Historical source snapshot {index} — unverified; excluded from current checks.",
                "Previous record retained when its source was " + entry["reason"] + ":",
            ]
        )
        for key, value in entry["record"].items():
            lines.extend(
                [
                    FIELD_LABELS[key] + " (historical, unverified):",
                    literal(value) if value else "Blank as recorded.",
                ]
            )
        if "assessment" in entry:
            old = entry["assessment"]
            label = WORKSTREAM_LABELS[old["status_field"]]
            lines.extend(
                [
                    "Previous " + label + " assessment (historical, unverified):",
                    literal(old["status"]),
                ]
            )
            if "date" in old:
                lines.extend(
                    [
                        "Previous " + label + " date (user-entered):",
                        literal(old["date"]) if old["date"] else "Blank as recorded.",
                    ]
                )
    return lines
