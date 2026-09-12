"""Local campaign planning with explicit evidence, exact costs and saved revisions.

Entered checks describe a person's assessment. They never establish eligibility.
Preparation does not fetch links, call a model, send messages or submit an application.
"""
from __future__ import annotations

import json
import re
import sqlite3
import uuid
from contextlib import contextmanager
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator

from .client import safe_url
from .evidence import literal, utc_now

SCHEMA = "sinter-campaign/v1"
MAX_DOCUMENT_BYTES = 1_000_000
MAX_TEXT_CHARACTERS = 200_000
MAX_CAMPAIGNS = 50
ROW_LIMITS = {"opportunities": 30, "requirements": 200, "answers": 100,
              "budget": 200, "actions": 200, "sources": 100}
OPPORTUNITY_STATUSES = frozenset({
    "researching", "open", "closed", "upcoming", "submitted", "paused",
    "clarification",
})
REQUIREMENT_STATUSES = frozenset({"unknown", "met", "not_met", "clarification"})
NOTICE = (
    "This campaign records your research and assessments. Checks and source links "
    "have not been independently verified. Confirm the current rules and final "
    "application with the funder; this pack does not determine eligibility."
)


def _object(value: object, fields: set[str], label: str) -> dict:
    if not isinstance(value, dict):
        raise ValueError(f"{label} must be an object.")
    if set(value) - fields:
        raise ValueError(f"{label} contains unsupported fields.")
    return value


def _text(value: object, label: str, limit: int,
          required: bool = False, strip: bool = False) -> str:
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError(f"{label} must be text of at most {limit:,} characters.")
    if any((ord(c) < 32 and c not in "\n\r\t") or 127 <= ord(c) <= 159
           or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise ValueError(f"{label} contains control characters or invalid Unicode.")
    if required and not value.strip():
        raise ValueError(f"Please enter {label.lower()}.")
    return value.strip() if strip else value


def _date(value: object, label: str) -> str:
    result = _text(value, label, 10)
    if result:
        try:
            if date.fromisoformat(result).isoformat() != result:
                raise ValueError()
        except ValueError as exc:
            raise ValueError(f"Use YYYY-MM-DD for {label.lower()}, or leave it "
                             "blank if it is unknown.") from exc
    return result


def _url(value: object, label: str) -> str:
    result = _text(value, label, 4000)
    if result and (not safe_url(result)
                   or any(c.isspace() or c in '<>"' for c in result)):
        raise ValueError(f"{label} must be an HTTP(S) link without credentials "
                         "or whitespace.")
    return result


def _status(value: object, choices: frozenset[str], label: str) -> str:
    result = _text(value, label, 30)
    if result not in choices:
        raise ValueError(f"Choose a valid {label.lower()}: "
                         + ", ".join(sorted(choices)) + ".")
    return result


def _money(value: object, label: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise ValueError(f"{label} must be a non-negative amount or null if unknown.")
    raw = str(value)
    if len(raw) > 30 or not re.fullmatch(r"\d+(?:\.\d{1,2})?", raw):
        raise ValueError(f"{label} needs a plain amount with at most two decimal "
                         "places, or null if unknown.")
    try:
        amount = Decimal(raw)
        if not amount.is_finite() or not 0 <= amount <= Decimal("1000000000"):
            raise ValueError()
        return format(amount.quantize(Decimal("0.01")), "f")
    except (ValueError, InvalidOperation) as exc:
        raise ValueError(f"{label} must be between 0 and 1,000,000,000.") from exc


def _integer(value: object, label: str, maximum: int) -> int:
    if isinstance(value, str) and re.fullmatch(r"\d{1,6}", value):
        value = int(value)
    if type(value) is not int or not 1 <= value <= maximum:
        raise ValueError(f"{label} must be a whole number from 1 to {maximum:,}.")
    return value


def _rows(data: dict, key: str, fields: set[str]) -> Iterator[dict]:
    rows = data.get(key, [])
    if not isinstance(rows, list) or len(rows) > ROW_LIMITS[key]:
        raise ValueError(f"Use at most {ROW_LIMITS[key]} {key} rows.")
    for index, row in enumerate(rows, 1):
        yield _object(row, fields, f"{key.capitalize()} row {index}")


def _reference(row: dict, names: set[str], optional: bool = False) -> str:
    name = _text(row.get("opportunity", ""), "Opportunity reference", 200,
                 not optional, strip=True)
    if name and name not in names:
        raise ValueError("An opportunity reference does not match an opportunity "
                         "name. Use the exact name, including capitalisation.")
    return name


def validate(data: object) -> dict:
    """Return a bounded, JSON-safe document, preserving incomplete work.

    Money is normalised to decimal strings with two places; null stays unknown.
    Unknown keys and broken opportunity references are rejected rather than lost.
    """
    data = _object(data, {"schema", "title", "organisation", "objective",
                          *ROW_LIMITS}, "Campaign")
    if data.get("schema", SCHEMA) != SCHEMA:
        raise ValueError("Choose a Sinter campaign document.")
    result = {"schema": SCHEMA,
              "title": _text(data.get("title", ""), "Campaign title", 200,
                             True, strip=True),
              "organisation": _text(data.get("organisation", ""),
                                    "Organisation", 1024, strip=True),
              "objective": _text(data.get("objective", ""), "Objective", 12000)}
    for key in ROW_LIMITS:
        result[key] = []
    names: set[str] = set()
    for row in _rows(data, "opportunities", {
        "name", "funder", "url", "deadline", "decision_window", "ceiling",
        "fit", "status",
    }):
        name = _text(row.get("name", ""), "Opportunity name", 200, True,
                     strip=True)
        if name.casefold() in {existing.casefold() for existing in names}:
            raise ValueError("Give each opportunity a distinct name.")
        names.add(name)
        result["opportunities"].append({
            "name": name,
            "funder": _text(row.get("funder", ""), "Funder", 300),
            "url": _url(row.get("url", ""), "Opportunity URL"),
            "deadline": _date(row.get("deadline", ""), "Application deadline"),
            "decision_window": _text(row.get("decision_window", ""),
                                     "Decision window", 1000),
            "ceiling": _money(row.get("ceiling"), "Funding ceiling"),
            "fit": _text(row.get("fit", ""), "Project fit", 6000),
            "status": _status(row.get("status", "researching"),
                              OPPORTUNITY_STATUSES, "opportunity status"),
        })
    for row in _rows(data, "requirements", {
        "opportunity", "rule", "status", "evidence", "source_url",
        "source_quote", "checked_at",
    }):
        result["requirements"].append({
            "opportunity": _reference(row, names),
            "rule": _text(row.get("rule", ""), "Requirement", 4000, True),
            "status": _status(row.get("status", "unknown"),
                              REQUIREMENT_STATUSES, "requirement status"),
            "evidence": _text(row.get("evidence", ""), "Applicant evidence", 6000),
            "source_url": _url(row.get("source_url", ""), "Requirement source URL"),
            "source_quote": _text(row.get("source_quote", ""),
                                  "Source wording", 4000),
            "checked_at": _date(row.get("checked_at", ""), "Date checked"),
        })
    for row in _rows(data, "answers", {
        "opportunity", "label", "text", "limit", "status",
    }):
        result["answers"].append({
            "opportunity": _reference(row, names),
            "label": _text(row.get("label", ""), "Answer label", 300, True),
            # Keep whitespace: the displayed count describes the exact draft.
            "text": _text(row.get("text", ""), "Answer text", 20000),
            "limit": (None if row.get("limit") is None else
                      _integer(row["limit"], "Answer character limit", 20000)),
            "status": _status(row.get("status", "draft"),
                              frozenset({"draft", "reviewed"}), "answer status"),
        })
    for row in _rows(data, "budget", {
        "item", "opportunity", "quantity", "unit_cost", "quote_reference",
    }):
        result["budget"].append({
            "item": _text(row.get("item", ""), "Budget item", 1000, True),
            "opportunity": _reference(row, names, optional=True),
            "quantity": _integer(row.get("quantity", 1), "Quantity", 100000),
            "unit_cost": _money(row.get("unit_cost"), "Unit cost"),
            "quote_reference": _text(row.get("quote_reference", ""),
                                     "Quote reference", 2000),
        })
    for row in _rows(data, "actions", {"task", "owner", "due", "status"}):
        result["actions"].append({
            "task": _text(row.get("task", ""), "Action", 4000, True),
            "owner": _text(row.get("owner", ""), "Action owner", 300),
            "due": _date(row.get("due", ""), "Action deadline"),
            "status": _status(row.get("status", "open"),
                              frozenset({"open", "done"}), "action status"),
        })
    for row in _rows(data, "sources", {"title", "url", "notes"}):
        result["sources"].append({
            "title": _text(row.get("title", ""), "Source title", 500, True),
            "url": _url(row.get("url", ""), "Source URL"),
            "notes": _text(row.get("notes", ""), "Source notes", 6000),
        })
    # Field and row limits bound validation before any combined encoding occurs.
    strings = [result["title"], result["organisation"], result["objective"]]
    strings.extend(value for key in ROW_LIMITS for row in result[key]
                   for value in row.values() if isinstance(value, str))
    if sum(map(len, strings)) > MAX_TEXT_CHARACTERS:
        raise ValueError("The campaign exceeds 200,000 text characters. "
                         "Split it into smaller campaigns.")
    encoded = json.dumps(result, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise ValueError("The campaign exceeds 1 MB. Split it into smaller campaigns.")
    return result


def _supported(row: dict) -> bool:
    return all(row[key].strip() for key in (
        "evidence", "source_url", "source_quote", "checked_at",
    ))


def _answer_metrics(rows: list[dict]) -> list[dict]:
    return [{"index": index, "opportunity": row["opportunity"],
             "label": row["label"], "characters": len(row["text"]),
             "words": len(row["text"].split()),
             "utf16_characters": sum(2 if ord(c) > 0xFFFF else 1
                                     for c in row["text"]),
             "limit": row["limit"],
             "over_limit": (row["limit"] is not None
                            and len(row["text"]) > row["limit"]),
             "remaining": (None if row["limit"] is None else
                           row["limit"] - len(row["text"]))}
            for index, row in enumerate(rows)]


def _budget_total(rows: list[dict]) -> dict:
    known = sum((Decimal(row["unit_cost"]) * row["quantity"] for row in rows
                 if row["unit_cost"] is not None), Decimal("0.00"))
    unknown = sum(row["unit_cost"] is None for row in rows)
    complete = bool(rows) and not unknown
    return {"known_total": format(known, ".2f"),
            "total": format(known, ".2f") if complete else None,
            "complete": complete, "unknown_costs": unknown,
            "unquoted_costs": sum(not row["quote_reference"].strip() for row in rows),
            "items": len(rows)}


def _budget_summary(document: dict) -> dict:
    result = _budget_total(document["budget"])
    groups = []
    for opportunity in document["opportunities"]:
        rows = [row for row in document["budget"]
                if row["opportunity"] == opportunity["name"]]
        totals = _budget_total(rows)
        ceiling = opportunity["ceiling"]
        # A known subtotal can already exceed a ceiling even with unknown lines.
        over = (Decimal(totals["known_total"]) > Decimal(ceiling)
                if ceiling is not None else None)
        groups.append({"opportunity": opportunity["name"], **totals,
                       "ceiling": ceiling, "over_ceiling": over})
    result["by_opportunity"] = groups
    result["unallocated_items"] = sum(not row["opportunity"]
                                      for row in document["budget"])
    return result


def _readiness(document: dict, metrics: list[dict], budget: dict) -> dict:
    checks = document["requirements"]
    unsupported = sum(row["status"] in {"met", "not_met"} and not _supported(row)
                      for row in checks)
    core_missing = [key for key in ("organisation", "objective", "opportunities")
                    if not document[key] or (isinstance(document[key], str)
                                             and not document[key].strip())]
    result = {
        "status": "human_review", "notice": NOTICE,
        "missing_sections": core_missing,
        "requirements_total": len(checks),
        "requirements_unresolved": sum(
            row["status"] in {"unknown", "clarification"} or not _supported(row)
            for row in checks),
        "requirements_not_met": sum(row["status"] == "not_met" for row in checks),
        "claims_without_evidence": unsupported,
        "opportunities_without_checks": sum(
            not any(row["opportunity"] == item["name"] for row in checks)
            for item in document["opportunities"]),
        "opportunities_without_sources": sum(not item["url"]
                                              for item in document["opportunities"]),
        "opportunities_without_answers": sum(
            not any(row["opportunity"] == item["name"]
                    for row in document["answers"])
            for item in document["opportunities"]),
        "answers_over_limit": sum(row["over_limit"] for row in metrics),
        "answers_empty": sum(not row["text"].strip() for row in document["answers"]),
        "answers_unreviewed": sum(row["status"] != "reviewed"
                                  for row in document["answers"]),
        "answer_limits_unknown": sum(row["limit"] is None for row in metrics),
        "budget_incomplete": not budget["complete"],
        "unknown_costs": budget["unknown_costs"],
        "unquoted_costs": budget["unquoted_costs"],
        "unallocated_budget_items": budget["unallocated_items"],
        "budgets_over_ceiling": sum(row["over_ceiling"] is True
                                    for row in budget["by_opportunity"]),
        "open_actions": sum(row["status"] == "open" for row in document["actions"]),
        "actions_without_owner": sum(
            row["status"] == "open" and not row["owner"].strip()
            for row in document["actions"]),
    }
    if core_missing or any(value for key, value in result.items()
                           if key not in {"status", "notice", "missing_sections",
                                          "requirements_total"}):
        result["status"] = "needs_attention"
    return result


def _inline(value: str) -> str:
    return literal(" ".join(value.split()))


def _link(url: str, label: str = "Source") -> str:
    # Angle-bracket destinations protect valid URL parentheses in Markdown.
    return f"[{_inline(label)}](<{url}>)" if url else "Source link not recorded"


def _amount(value: str | None) -> str:
    return "Not yet costed" if value is None else format(Decimal(value), ",.2f")


def _render(document: dict, readiness: dict, metrics: list[dict],
            budget: dict) -> str:
    lines = ["# " + _inline(document["title"])]
    if document["organisation"]:
        lines.append(_inline(document["organisation"]))
    if document["objective"].strip():
        lines.extend(["## Project objective", literal(document["objective"])])
    lines.extend(["## Work still to complete",
                  f"{readiness['requirements_unresolved']} requirements unresolved; "
                  f"{readiness['requirements_not_met']} marked not met; "
                  f"{readiness['answers_over_limit']} answers over their limits; "
                  f"{readiness['unquoted_costs']} budget items without quotes; "
                  f"{readiness['open_actions']} open actions.", NOTICE])
    if readiness["missing_sections"]:
        lines.append("Add: " + ", ".join(readiness["missing_sections"]) + ".")
    if readiness["claims_without_evidence"]:
        lines.append(f"{readiness['claims_without_evidence']} marked checks need "
                     "applicant evidence, source wording, a source link "
                     "or a date checked.")
    if readiness["opportunities_without_checks"]:
        lines.append(f"{readiness['opportunities_without_checks']} opportunities have "
                     "no recorded requirements yet.")
    for item in document["opportunities"]:
        name = item["name"]
        lines.extend(["## " + _inline(name),
                      "Funder: " + _inline(item["funder"] or "Not recorded")
                      + " · Status entered: " + item["status"],
                      "Application deadline: " + (item["deadline"] or "Not confirmed")
                      + " · Funding ceiling: " + _amount(item["ceiling"]),
                      "Decision window: " + _inline(item["decision_window"]
                                                    or "Not confirmed"),
                      _link(item["url"], "Programme details")])
        if item["fit"].strip():
            lines.extend(["### Fit with the project", literal(item["fit"])])
        rows = [row for row in document["requirements"] if row["opportunity"] == name]
        lines.append("### Requirement checks")
        if not rows:
            lines.append("No requirements have been recorded for this opportunity.")
        for row in rows:
            label = {"met": "Marked met", "not_met": "Marked not met",
                     "unknown": "Not confirmed",
                     "clarification": "Clarification needed"}
            state = label[row["status"]]
            if row["status"] in {"met", "not_met"} and not _supported(row):
                state += " — supporting evidence incomplete"
            lines.extend(["**" + state + ":** " + literal(row["rule"]),
                          "Applicant evidence: " + literal(row["evidence"]
                                                            or "Not recorded"),
                          "Source wording: " + literal(row["source_quote"]
                                                       or "Not recorded"),
                          _link(row["source_url"]) + " · Date checked: "
                          + (row["checked_at"] or "Not recorded")])
        lines.append("### Application answers")
        indexes = [index for index, row in enumerate(document["answers"])
                   if row["opportunity"] == name]
        if not indexes:
            lines.append("No application answers have been recorded yet.")
        for index in indexes:
            row, count = document["answers"][index], metrics[index]
            limit = ("limit not recorded" if count["limit"] is None
                     else f"limit {count['limit']}")
            lines.extend(["#### " + _inline(row["label"]),
                          f"{count['characters']} characters · "
                          f"{count['words']} words · "
                          f"{limit} · {row['status']}"
                          + (" · OVER LIMIT" if count["over_limit"] else ""),
                          literal(row["text"]) if row["text"].strip()
                          else "Answer not drafted yet."])
    lines.append("## Budget")
    if not document["budget"]:
        lines.append("No budget items have been recorded. "
                     "The project total is unknown.")
    else:
        lines.extend(["| Item | Opportunity | Quantity | Unit cost | Line total "
                      "| Quote |",
                      "| --- | --- | ---: | ---: | ---: | --- |"])
        for row in document["budget"]:
            total = (None if row["unit_cost"] is None else
                     str(Decimal(row["unit_cost"]) * row["quantity"]))
            cells = [_inline(row["item"]), _inline(row["opportunity"] or "Unallocated"),
                     str(row["quantity"]), _amount(row["unit_cost"]), _amount(total),
                     _inline(row["quote_reference"] or "Quote needed")]
            lines.append("| " + " | ".join(cells) + " |")
        if budget["complete"]:
            lines.append("**Total entered cost: " + _amount(budget["total"]) + "**")
        else:
            lines.append("**Known subtotal: " + _amount(budget["known_total"])
                         + f". Total incomplete: {budget['unknown_costs']} items "
                         "still need costs.**")
        for group in budget["by_opportunity"]:
            if group["items"]:
                lines.append(_inline(group["opportunity"]) + ": "
                             + _amount(group["known_total"])
                             + (" known subtotal" if not group["complete"]
                                else " allocated")
                             + (" — exceeds the entered funding ceiling."
                                if group["over_ceiling"] else "."))
    lines.append("## Next actions")
    if not document["actions"]:
        lines.append("No actions have been recorded yet.")
    for row in document["actions"]:
        lines.append("- " + _inline(row["task"]) + " · Owner: "
                     + _inline(row["owner"] or "Unassigned") + " · Due: "
                     + (row["due"] or "Not set") + " · " + row["status"])
    if document["sources"]:
        lines.append("## Source references")
        for row in document["sources"]:
            lines.append("### " + _inline(row["title"]))
            lines.append(_link(row["url"]))
            if row["notes"].strip():
                lines.append(literal(row["notes"]))
    lines.append("Character counts use Unicode code points, including whitespace. "
                 "Check the receiving form's own counter when pasting answers.")
    # Keep table rows adjacent; ordinary blocks have a blank line between them.
    output = ""
    previous_table = False
    for line in lines:
        is_table = line.startswith("| ")
        output += ("\n" if is_table and previous_table else "\n\n") + line
        previous_table = is_table
    return output.lstrip() + "\n"


def prepare(data: object) -> dict:
    """Prepare a readable campaign pack and derived checks without network access."""
    campaign = validate(data)
    metrics = _answer_metrics(campaign["answers"])
    budget = _budget_summary(campaign)
    readiness = _readiness(campaign, metrics, budget)
    markdown = _render(campaign, readiness, metrics, budget)
    return {"workflow": "campaign", "title": campaign["title"],
            "document_title": campaign["title"], "created_at": utc_now(),
            "review_status": "user_entered", "campaign": campaign,
            "readiness": readiness, "answer_metrics": metrics,
            "budget_summary": budget, "document_markdown": markdown,
            "markdown": markdown}


class CampaignStore:
    """Save campaign documents atomically, protecting edits across browser tabs."""

    def __init__(self, directory: str | Path):
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        self.path = directory / "campaigns.sqlite3"
        with self._connect() as db:
            db.execute("CREATE TABLE IF NOT EXISTS campaigns "
                       "(id TEXT PRIMARY KEY, revision INTEGER NOT NULL, "
                       "title TEXT NOT NULL, updated_at TEXT NOT NULL, "
                       "document TEXT NOT NULL)")

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        db = sqlite3.connect(self.path, timeout=5)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    @staticmethod
    def _identifier(value: object) -> str:
        if not isinstance(value, str) or not re.fullmatch(r"[0-9a-f]{32}", value):
            raise ValueError("Use a valid saved campaign ID.")
        return value

    @staticmethod
    def _revision(value: object) -> int:
        if type(value) is not int or not 1 <= value < 2_147_483_647:
            raise ValueError("Reopen the campaign to obtain its current revision.")
        return value

    def save(self, document: object, id: str | None = None,
             revision: int | None = None) -> dict:
        """Create a campaign or replace exactly the revision the caller edited."""
        normalized = validate(document)
        encoded = json.dumps(normalized, ensure_ascii=False, allow_nan=False)
        if id is None and revision is not None:
            raise ValueError("A revision must identify an existing campaign.")
        if id is not None:
            id, revision = self._identifier(id), self._revision(revision)
        with self._connect() as db:
            db.execute("BEGIN IMMEDIATE")
            if id is None:
                count = db.execute("SELECT count(*) FROM campaigns").fetchone()[0]
                if count >= MAX_CAMPAIGNS:
                    raise ValueError("You have 50 campaigns. Export and remove an "
                                     "old campaign before creating another.")
                id, revision = uuid.uuid4().hex, 1
                db.execute("INSERT INTO campaigns VALUES (?,?,?,?,?)",
                           (id, revision, normalized["title"], utc_now(), encoded))
            else:
                cursor = db.execute(
                    "UPDATE campaigns SET revision=revision+1,title=?,updated_at=?,"
                    "document=? WHERE id=? AND revision=?",
                    (normalized["title"], utc_now(), encoded, id, revision))
                if cursor.rowcount != 1:
                    raise ValueError("This campaign changed in another window or "
                                     "was removed. Export your edits, then reopen it.")
                revision += 1
        return {"id": id, "revision": revision, "document": normalized}

    def list(self) -> list[dict]:
        """List saved campaign identities and revisions without their private text."""
        with self._connect() as db:
            return [dict(row) for row in db.execute(
                "SELECT id,revision,title,updated_at FROM campaigns "
                "ORDER BY updated_at DESC,id")]

    def get(self, id: str) -> dict:
        """Read one campaign; a removed identity raises KeyError."""
        id = self._identifier(id)
        with self._connect() as db:
            row = db.execute("SELECT revision,document FROM campaigns WHERE id=?",
                             (id,)).fetchone()
        if row is None:
            raise KeyError("Campaign not found.")
        return {"id": id, "revision": row["revision"],
                "document": json.loads(row["document"])}

    def delete(self, id: str, revision: int) -> None:
        """Remove only the revision reviewed by the caller."""
        id, revision = self._identifier(id), self._revision(revision)
        with self._connect() as db:
            cursor = db.execute("DELETE FROM campaigns WHERE id=? AND revision=?",
                                (id, revision))
            if cursor.rowcount != 1:
                raise ValueError("This campaign changed or was removed. "
                                 "Reopen it before deleting.")
