"""Conservative comparisons of human-entered grant requirements, not eligibility decisions."""
from __future__ import annotations

import math
from datetime import date, timedelta

from .evidence import Source, literal, text

FIELDS = {"organisation_type", "location", "budget"}


def _requirement_source(rule: dict, sources: list[Source],
                        by_id: dict[str, Source]) -> tuple[str, Source | None]:
    """Resolve an exact, unique title to its evidence identity without changing trust."""
    identifier = text(rule.get("source_id", ""), "Source ID", 100)
    if "source_title" not in rule:
        return identifier, by_id.get(identifier)
    title = text(rule["source_title"], "Source title", 500, True)
    matches = {item.id: item for item in sources if item.title == title}
    if not matches:
        raise ValueError("No source has that exact source_title. Copy a source title "
                         "exactly, including its capitalisation and spacing.")
    if len(matches) != 1:
        raise ValueError("That source_title matches more than one source. Give the "
                         "sources distinct titles or use source_id alone.")
    ref = next(iter(matches.values()))
    if identifier and identifier != ref.id:
        raise ValueError("source_id and source_title identify different sources. "
                         "Use one selector or make both identify the same source.")
    return ref.id, ref


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
        identifier, ref = _requirement_source(rule, sources, by_id)
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
        elif (actual is None or expected is None
              or (isinstance(actual, str) and not actual.strip())
              or (isinstance(expected, str) and not expected.strip())):
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
                       "source_title": ref.title if ref else "",
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
    try:
        parsed + timedelta(days=1)
    except OverflowError as exc:
        raise ValueError("The deadline has no representable calendar end date.") from exc
    return value
