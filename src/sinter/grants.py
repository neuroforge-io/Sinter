"""Conservative comparisons of human-entered grant requirements, not eligibility decisions."""
from __future__ import annotations

import math
from datetime import date

from .evidence import Source, literal, text

FIELDS = {"organisation_type", "location", "budget"}


def screen(profile: dict, criteria: list[dict], sources: list[Source]) -> dict:
    if not isinstance(profile, dict) or not isinstance(criteria, list) or len(criteria) > 30:
        raise ValueError("Provide an organisation profile and up to 30 requirements.")
    by_id = {item.id: item for item in sources}
    checks = []
    for rule in criteria:
        if not isinstance(rule, dict):
            raise ValueError("Each requirement must be an object.")
        field, op = rule.get("field"), rule.get("operator")
        if not isinstance(field, str) or not isinstance(op, str) or field not in FIELDS or op not in {"equals", "contains", "minimum", "maximum"}:
            raise ValueError("Unsupported profile field or comparison.")
        quote = text(rule.get("quote", ""), "Requirement wording", 4000)
        identifier = text(rule.get("source_id", ""), "Source ID", 100)
        ref = by_id.get(identifier)
        actual, expected = profile.get(field), rule.get("value")
        if isinstance(actual, (dict, list)) or isinstance(expected, (dict, list)):
            raise ValueError("Requirement and profile values must be text or numbers.")
        status, reason = "unknown", "Check this requirement against the current official guidelines."
        if not ref or not quote.strip() or quote not in ref.content:
            reason = "The exact requirement wording is missing or does not match its source."
        elif ref.kind in {"sample", "user_note", "transcript"}:
            reason = "Notes, examples and transcripts cannot establish official grant requirements."
        elif rule.get("confirmed") is not True:
            reason = "A person must confirm the source is current, official and correctly interpreted."
        elif actual is None or actual == "" or expected is None or expected == "":
            reason = "The profile or required value is missing."
        else:
            try:
                if op in {"minimum", "maximum"}:
                    if isinstance(actual, bool) or isinstance(expected, bool):
                        raise ValueError("boolean is not a budget")
                    a, b = float(actual), float(expected)
                    if not math.isfinite(a) or not math.isfinite(b):
                        raise ValueError("non-finite value")
                    passed = a >= b if op == "minimum" else a <= b
                else:
                    if not isinstance(actual, str) or not isinstance(expected, str):
                        raise ValueError("text comparison requires text")
                    a, b = actual.strip().casefold(), expected.strip().casefold()
                    passed = a == b if op == "equals" else b in a
                status = "met" if passed else "not_met"
                reason = "Matches the entered requirement." if passed else "Does not match the entered requirement."
            except (ValueError, TypeError, OverflowError):
                reason = "The values cannot be compared; check units and values."
        checks.append({"field": field, "status": status, "reason": reason, "source_id": identifier,
                       "quote": quote, "operator": op, "actual": actual, "expected": expected})
    notice = ("These are checks of entered requirements, not an eligibility determination. "
              "Confirm every condition, exclusion, deadline and applicant detail with the funder.")
    markdown = ["## Human-entered requirement checks", notice]
    for row in checks:
        markdown.append(f"- {row['field']}: {row['status']}. {row['reason']} "
                        f"Entered: {literal(str(row['actual']))}; {row['operator']} {literal(str(row['expected']))}. "
                        f"[{row['source_id']}] Requirement: {literal(row['quote'])}")
    return {"status": "review_required", "checks": checks, "notice": notice, "markdown": "\n\n".join(markdown)}


def confirmed_deadline(value: str) -> str:
    try:
        parsed = date.fromisoformat(value)
    except (ValueError, TypeError) as exc:
        raise ValueError("Use a confirmed deadline in YYYY-MM-DD format.") from exc
    if parsed.isoformat() != value:
        raise ValueError("Use YYYY-MM-DD for a deadline.")
    return value
