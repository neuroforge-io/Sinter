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
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Iterator

from .campaign_capacity import text_characters
from .campaign_currency import (
    can_compare_ceiling,
    ceiling_comparison_note,
    ceiling_currency,
    funding_amount,
)
from .client import safe_url
from .evidence import literal, utc_now

SCHEMA = "sinter-campaign/v1"
ACTIONABLE_OPPORTUNITY_STATES = frozenset({"researching", "open", "upcoming", "clarification"})
MAX_DOCUMENT_BYTES = 1_000_000
MAX_TEXT_CHARACTERS = 200_000
MAX_CAMPAIGNS = 50
WINDOW_CHECK_MAX_AGE_DAYS = 90
ROW_LIMITS = {"opportunities": 30, "requirements": 200, "answers": 100,
              "budget": 200, "actions": 200, "sources": 100,
              "communications": 200, "assets": 60}
OPPORTUNITY_STATUSES = frozenset({
    "researching", "open", "closed", "upcoming", "submitted", "paused",
    "clarification", "not_pursuing",
})
OPPORTUNITY_TYPES = frozenset({
    "unknown", "cash_grant", "matched_voucher", "tax_incentive",
    "equity", "non_cash_support", "other",
})
APPLICATION_MODES = frozenset({"unknown", "required", "not_required"})
REQUIREMENT_STATUSES = frozenset({"unknown", "met", "not_met", "clarification"})
COMMUNICATION_DIRECTIONS = frozenset({"incoming", "outgoing"})
COMMUNICATION_STATUSES = frozenset({"draft", "received", "sent"})
COMMUNICATION_CHANNELS = frozenset({"email", "letter", "phone", "meeting",
                                    "portal", "other"})
ACTION_SUBMISSION_PHASES = frozenset({"pre_submission", "post_submission"})
ACTION_OWNER_KINDS = frozenset({"unknown", "person", "role", "unassigned"})
MAX_COMMUNICATION_EVIDENCE_LINKS = 10
MAX_ASSET_REFERENCES = 20
ASSET_KINDS = frozenset({"product", "service", "research", "prototype",
                         "brand", "dataset", "model", "other"})
ASSET_STAGES = frozenset({"unknown", "concept", "prototype", "pilot",
                          "released", "retired"})
ASSET_CONTRIBUTOR_STATUSES = frozenset({
    "unknown", "contributors_identified", "records_to_check", "evidence_recorded",
})
ASSET_RIGHTS_STATUSES = frozenset({
    "unknown", "records_to_check", "public_license_stated", "evidence_recorded",
})
ASSET_DISCLOSURE_STATUSES = frozenset({"unknown", "records_to_check", "date_recorded"})
ASSET_PRIOR_ART_STATUSES = frozenset({
    "not_started", "leads_recorded", "preliminary_screen", "specialist_review_pending",
})
ASSET_REFERENCE_KINDS = frozenset({
    "public_claim", "prior_art", "rights", "contributors", "disclosure", "other",
})
INVALID_TEXT_CHARACTERS = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ud800-\udfff]"
)
NOTICE = (
    "This campaign records your research and assessments. Checks and source links "
    "have not been independently verified. Confirm the current rules and final "
    "application with the funder; this pack does not determine eligibility."
)
ASSET_KIND_LABELS = {
    "product": "Product", "service": "Service", "research": "Research",
    "prototype": "Prototype", "brand": "Brand", "dataset": "Dataset",
    "model": "Model", "other": "Other",
}
ASSET_STAGE_LABELS = {
    "unknown": "Not recorded", "concept": "Concept", "prototype": "Prototype",
    "pilot": "Pilot", "released": "Released", "retired": "Retired",
}
ASSET_CONTRIBUTOR_LABELS = {
    "unknown": "Not checked", "contributors_identified": "Contributors identified",
    "records_to_check": "Records to check", "evidence_recorded": "Reference recorded",
}
ASSET_RIGHTS_LABELS = {
    "unknown": "Not checked", "records_to_check": "Records to check",
    "public_license_stated": "Public licence stated; title not established",
    "evidence_recorded": "Reference recorded; unverified",
}
ASSET_DISCLOSURE_LABELS = {
    "unknown": "Not checked", "records_to_check": "Records to check",
    "date_recorded": "Date recorded; unverified",
}
ASSET_PRIOR_ART_LABELS = {
    "not_started": "Not started", "leads_recorded": "Leads recorded",
    "preliminary_screen": "Preliminary screen recorded; no legal conclusion",
    "specialist_review_pending": "Specialist review pending",
}
ASSET_REFERENCE_LABELS = {
    "public_claim": "Public description", "prior_art": "Prior-art lead",
    "rights": "Rights record", "contributors": "Contributor record",
    "disclosure": "Disclosure record", "other": "Other evidence",
}


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
    if INVALID_TEXT_CHARACTERS.search(value):
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


def _action_owner_is_role_suggestion(owner: str) -> bool:
    return bool(re.search(r"(?i)\b(?:suggested|role suggestion)\b", owner))


def _action_owner_label(owner: str) -> str:
    return re.sub(r"(?i)\s*\((?:suggested|suggested role)\)\s*$", "",
                  owner.strip()).strip()


def _infer_action_owner_kind(owner: str) -> str:
    if not owner.strip() or re.search(r"(?i)\bunassigned\b", owner):
        return "unassigned"
    if _action_owner_is_role_suggestion(owner):
        return "role"
    # Historical records used one field for both roles and people, so even a
    # checked legacy acceptance flag cannot safely establish the owner type.
    return "unknown"


def _action_owner_summary(owner: str, kind: str, accepted: bool) -> str:
    value = owner.strip()
    if kind == "unassigned" or not value or re.search(r"(?i)\bunassigned\b", value):
        return "No person named; owner needed"
    if kind == "role":
        label = _action_owner_label(value) or value
        return "Suggested role only; no person named (" + _inline(label) + ")"
    if kind == "unknown":
        return "Owner type not confirmed: " + _inline(value)
    if accepted:
        return ("Named person: " + _inline(value)
                + "; user-marked accepted, not independently verified")
    return "Named person: " + _inline(value) + "; acceptance unconfirmed"


def _action_is_current(row: dict, opportunities: list[dict]) -> bool:
    """Only show actions whose confirmed scope and submission phase match now."""
    if row["status"] == "held":
        return False
    if not row["scope_confirmed"]:
        return False
    if not row["opportunity"]:
        return True
    route = next((item for item in opportunities
                  if item["name"] == row["opportunity"]), None)
    if route is None:
        return False
    if route["status"] in ACTIONABLE_OPPORTUNITY_STATES:
        return row["submission_phase"] != "post_submission"
    return (route["status"] == "submitted"
            and row["submission_phase"] == "post_submission")


def validate(data: object) -> dict:
    """Return a bounded, JSON-safe document, preserving incomplete work.

    Money is normalised to decimal strings with two places; null stays unknown.
    Unknown keys and broken opportunity references are rejected rather than lost.
    """
    data = _object(data, {"schema", "title", "organisation", "objective",
                          "signatory", "sender_role", "contact_details",
                          *ROW_LIMITS}, "Campaign")
    if data.get("schema", SCHEMA) != SCHEMA:
        raise ValueError("Choose a Sinter campaign document.")
    result = {"schema": SCHEMA,
              "title": _text(data.get("title", ""), "Campaign title", 200,
                             True, strip=True),
              "organisation": _text(data.get("organisation", ""),
                                    "Organisation", 1024, strip=True),
              "objective": _text(data.get("objective", ""), "Objective", 12000),
              "signatory": _text(data.get("signatory", ""),
                                  "Authorised campaign signatory", 200, strip=True),
              "sender_role": _text(data.get("sender_role", ""),
                                   "Campaign signatory role", 200, strip=True),
              "contact_details": _text(data.get("contact_details", ""),
                                       "Campaign contact details", 4096, strip=True)}
    for key in ROW_LIMITS:
        result[key] = []
    source_ids: set[str] = set()
    for row in _rows(data, "sources", {
        "id", "title", "url", "notes", "checked_at",
    }):
        if not any(str(row.get(key, "")).strip()
                   for key in ("title", "url", "notes")):
            # Empty Add-source rows are editor placeholders, not source records.
            continue
        title = _text(row.get("title", ""), "Source title", 500, True, strip=True)
        url = _url(row.get("url", ""), "Source URL")
        source_id = row.get("id") or uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"sinter-campaign-source:{title.casefold()}\x1f{url.casefold()}").hex
        if not isinstance(source_id, str) or not re.fullmatch(r"[0-9a-f]{32}", source_id):
            raise ValueError("Each campaign source needs a valid stable record ID.")
        if source_id in source_ids:
            raise ValueError("Give each campaign source a distinct record ID.")
        source_ids.add(source_id)
        result["sources"].append({
            "id": source_id,
            "title": title,
            "url": url,
            "notes": _text(row.get("notes", ""), "Source notes", 6000),
            "checked_at": _date(row.get("checked_at", ""), "Source check date"),
        })
    source_by_id = {source["id"]: source for source in result["sources"]}
    names: set[str] = set()
    for row in _rows(data, "opportunities", {
        "name", "funder", "url", "deadline", "application_window",
        "window_source_id", "window_source_url", "window_source_quote",
        "window_checked_at", "decision_window",
        "ceiling", "ceiling_currency", "fit", "status", "route_type", "application_mode", "applicant",
        "applicant_confirmed",
    }):
        name = _text(row.get("name", ""), "Opportunity name", 200, True,
                     strip=True)
        if name.casefold() in {existing.casefold() for existing in names}:
            raise ValueError("Give each opportunity a distinct name.")
        names.add(name)
        deadline = _date(row.get("deadline", ""), "Application deadline")
        # Documents saved before application-window tracking infer a fixed
        # window from their existing deadline; blank legacy dates remain unknown.
        window = row.get("application_window",
                         "fixed" if deadline else "unknown")
        window_source_id = _text(row.get("window_source_id", ""),
                                 "Application-window source ID", 32)
        if window_source_id and window_source_id not in source_by_id:
            raise ValueError("An application-window check points to a campaign source that no longer exists.")
        applicant = _text(row.get("applicant", ""), "Route applicant", 300)
        application_mode = _status(
            row.get("application_mode", "unknown"), APPLICATION_MODES,
            "application workflow")
        applicant_confirmed = row.get("applicant_confirmed", False)
        if type(applicant_confirmed) is not bool:
            raise ValueError("Route applicant confirmation must be true or false.")
        if applicant_confirmed and (
                application_mode != "required"
                or not applicant.strip()):
            raise ValueError("Confirm an applicant only after recording a named applicant for a required application.")
        result["opportunities"].append({
            "name": name,
            "funder": _text(row.get("funder", ""), "Funder", 300),
            "url": _url(row.get("url", ""), "Opportunity URL"),
            "deadline": deadline,
            "application_window": _status(
                window, frozenset({"unknown", "fixed", "rolling"}),
                "application window"),
            "window_source_id": window_source_id,
            # Keep the exact page URL beside the quote. A later edit to the
            # source register must not silently refresh an older window claim.
            "window_source_url": _url(row.get("window_source_url", ""),
                                       "Application-window source URL"),
            "window_source_quote": _text(
                row.get("window_source_quote", ""),
                "Application-window source wording", 2000),
            "window_checked_at": _date(
                row.get("window_checked_at", ""),
                "Application-window date checked"),
            "decision_window": _text(row.get("decision_window", ""),
                                     "Decision window", 1000),
            "ceiling": _money(row.get("ceiling"), "Funding ceiling"),
            "fit": _text(row.get("fit", ""), "Project fit", 6000),
            "route_type": _status(row.get("route_type", "unknown"),
                                   OPPORTUNITY_TYPES, "route type"),
            "application_mode": application_mode,
            "applicant": applicant,
            "applicant_confirmed": applicant_confirmed,
            "status": _status(row.get("status", "researching"),
                              OPPORTUNITY_STATUSES, "opportunity status"),
        })
        currency = ceiling_currency(row)
        # Preserve legacy AUD serialization; an explicit different denomination
        # is part of the saved input, never an FX hint.
        if currency != "AUD":
            result["opportunities"][-1]["ceiling_currency"] = currency
    for row in _rows(data, "requirements", {
        "opportunity", "rule", "status", "evidence", "source_id", "source_url",
        "source_quote", "checked_at",
    }):
        source_id = _text(row.get("source_id", ""),
                          "Requirement campaign source ID", 32)
        if source_id and source_id not in source_by_id:
            raise ValueError("A requirement points to a campaign source that no longer exists.")
        linked_source = source_by_id.get(source_id)
        result["requirements"].append({
            "opportunity": _reference(row, names),
            "rule": _text(row.get("rule", ""), "Requirement", 4000, True),
            "status": _status(row.get("status", "unknown"),
                              REQUIREMENT_STATUSES, "requirement status"),
            "evidence": _text(row.get("evidence", ""), "Applicant evidence", 6000),
            "source_id": source_id,
            # Keep the URL and date captured with this exact excerpt. A refreshed
            # registry record must not silently rewrite or date old evidence.
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
    for row in _rows(data, "actions", {
        "opportunity", "scope_confirmed", "submission_phase", "task", "owner",
        "owner_kind", "owner_confirmed", "due", "status",
    }):
        owner = _text(row.get("owner", ""), "Action owner", 300)
        owner_confirmed = row.get("owner_confirmed", False)
        if type(owner_confirmed) is not bool:
            raise ValueError("Action owner confirmation must be true or false.")
        has_owner_kind = "owner_kind" in row
        owner_kind = (_infer_action_owner_kind(owner)
                      if not has_owner_kind else
                      _status(row["owner_kind"], ACTION_OWNER_KINDS,
                              "action owner type"))
        if not has_owner_kind and owner_kind != "person":
            # Earlier releases let a role suggestion carry a checked acceptance
            # box. Preserve the suggestion but discard that invalid old signal.
            owner_confirmed = False
        if owner_kind == "unknown" and _action_owner_is_role_suggestion(owner):
            owner_kind = "role"
        if not owner.strip() or re.search(r"(?i)\bunassigned\b", owner):
            owner_kind = "unassigned"
        if owner_kind in {"person", "role", "unknown"} and not owner.strip():
            raise ValueError("Enter an owner entry or choose no owner assigned.")
        if owner_kind == "unassigned" and owner.strip() and not re.search(
                r"(?i)\bunassigned\b", owner):
            raise ValueError("Choose a named person or suggested role for this owner entry.")
        if owner_kind == "person" and _action_owner_is_role_suggestion(owner):
            raise ValueError("A suggested role cannot be recorded as a named person.")
        scope_confirmed = row.get("scope_confirmed", "opportunity" in row)
        if type(scope_confirmed) is not bool:
            raise ValueError("Action scope confirmation must be true or false.")
        if owner_confirmed and owner_kind != "person":
            raise ValueError("Confirm acceptance only after recording a named person's agreement.")
        result["actions"].append({
            "opportunity": _reference(row, names, optional=True),
            "scope_confirmed": scope_confirmed,
            "submission_phase": _status(
                row.get("submission_phase", "pre_submission"),
                ACTION_SUBMISSION_PHASES, "action submission phase"),
            "task": _text(row.get("task", ""), "Action", 4000, True),
            "owner": owner,
            "owner_kind": owner_kind,
            "owner_confirmed": owner_confirmed,
            "due": _date(row.get("due", ""), "Action deadline"),
            "status": _status(row.get("status", "open"),
                              frozenset({"open", "held", "done"}), "action status"),
        })
    asset_names: set[str] = set()
    asset_ids: set[str] = set()
    for row in _rows(data, "assets", {
        "id", "name", "kind", "stage", "public_summary", "public_url",
        "differentiation_question", "contributors_status", "contributor_notes",
        "rights_status", "rights_notes", "disclosure_status",
        "first_public_date", "disclosure_notes", "prior_art_status",
        "prior_art_notes", "prior_art_checked_at", "funding_opportunities",
        "references",
    }):
        name = _text(row.get("name", ""), "Product or asset name", 250, True,
                     strip=True)
        if name.casefold() in {existing.casefold() for existing in asset_names}:
            raise ValueError("Give each product or asset a distinct name.")
        asset_names.add(name)
        asset_id = row.get("id") or uuid.uuid5(
            uuid.NAMESPACE_URL, f"sinter-campaign-asset:{name.casefold()}").hex
        if not isinstance(asset_id, str) or not re.fullmatch(r"[0-9a-f]{32}", asset_id):
            raise ValueError("Each product or asset needs a valid stable record ID.")
        if asset_id in asset_ids:
            raise ValueError("Give each product or asset a distinct record ID.")
        asset_ids.add(asset_id)
        funding_opportunities = row.get("funding_opportunities", [])
        if (not isinstance(funding_opportunities, list)
                or len(funding_opportunities) > 10):
            raise ValueError("Choose at most 10 funding routes to assess for each "
                             "product or asset.")
        normalized_funding_opportunities = []
        for reference in funding_opportunities:
            opportunity = _text(reference, "Funding route reference", 200,
                                True, strip=True)
            if opportunity not in names:
                raise ValueError("An asset funding route does not match an "
                                 "opportunity name. Use the exact name.")
            if opportunity in normalized_funding_opportunities:
                raise ValueError("Choose each funding route only once per asset.")
            normalized_funding_opportunities.append(opportunity)
        references = row.get("references", [])
        if not isinstance(references, list) or len(references) > MAX_ASSET_REFERENCES:
            raise ValueError(f"Use at most {MAX_ASSET_REFERENCES} evidence references "
                             "for each product or asset.")
        normalized_references = []
        for index, reference in enumerate(references, 1):
            reference = _object(reference, {
                "kind", "source_id", "title", "url", "excerpt", "checked_at",
                "notes",
            },
                                f"Asset evidence reference {index}")
            source_id = _text(reference.get("source_id", ""),
                              "Linked campaign source ID", 32)
            if source_id and source_id not in source_ids:
                raise ValueError("An asset evidence reference points to a campaign source that no longer exists.")
            if not source_id and not any(str(reference.get(key, "")).strip()
                                         for key in ("title", "url", "excerpt", "notes")):
                # An untouched Add-reference row is an editor placeholder, not
                # evidence. Ignore it so a user can back out without a save error.
                continue
            linked_source = next((source for source in result["sources"]
                                  if source["id"] == source_id), None)
            # A linked reference is a snapshot of the source used for this
            # passage. Keep populated snapshot fields when the source register
            # is refreshed; fill them from the source only when first linking.
            if linked_source and not str(reference.get("title", "")).strip():
                title = linked_source["title"]
            else:
                title = _text(reference.get("title", ""),
                              "Asset evidence title", 500, True, strip=True)
            if "url" in reference:
                url = _url(reference.get("url", ""), "Asset evidence URL")
            else:
                url = linked_source["url"] if linked_source else ""
            checked_at = reference.get("checked_at", "")
            if "checked_at" not in reference and linked_source:
                checked_at = linked_source["checked_at"]
            normalized_references.append({
                "kind": _status(reference.get("kind", "other"),
                                ASSET_REFERENCE_KINDS, "asset evidence type"),
                "source_id": source_id,
                "title": title,
                "url": url,
                "excerpt": _text(reference.get("excerpt", ""),
                                 "Relevant source passage", 3000),
                "checked_at": _date(checked_at, "Asset reference check date"),
                "notes": _text(reference.get("notes", ""),
                               "Asset evidence note", 2000),
            })
        reference_kinds = {reference["kind"] for reference in normalized_references}
        if (row.get("contributors_status") == "evidence_recorded"
                and "contributors" not in reference_kinds):
            raise ValueError("Add a contributor evidence reference or mark the record as not checked.")
        if (row.get("rights_status") in {"public_license_stated", "evidence_recorded"}
                and "rights" not in reference_kinds):
            raise ValueError("Add a rights evidence reference or mark the record as not checked.")
        if (row.get("prior_art_status") in {"leads_recorded", "preliminary_screen"}
                and not any(reference["kind"] == "prior_art"
                            and (reference["source_id"] or reference["url"])
                            for reference in normalized_references)):
            raise ValueError("Add a prior-art evidence reference with a public link or mark the research as not started.")
        if row.get("prior_art_status") == "preliminary_screen" and not any(
                reference["kind"] == "prior_art" and reference["source_id"]
                and reference["excerpt"].strip() and reference["checked_at"]
                for reference in normalized_references):
            raise ValueError("Record a checked source, date and relevant passage before marking a preliminary screen.")
        disclosure_date = _date(row.get("first_public_date", ""),
                                "First public disclosure date")
        disclosure_status = _status(
            row.get("disclosure_status", "unknown"), ASSET_DISCLOSURE_STATUSES,
            "disclosure record status")
        if disclosure_status == "date_recorded" and not disclosure_date:
            raise ValueError("Record a first public disclosure date or mark it not checked.")
        if disclosure_status == "date_recorded" and not any(
                reference["kind"] == "disclosure" and reference["source_id"]
                and reference["excerpt"].strip() and reference["checked_at"]
                for reference in normalized_references):
            raise ValueError("Add a checked disclosure source, date and relevant passage before recording a disclosure date.")
        result["assets"].append({
            "id": asset_id,
            "name": name,
            "kind": _status(row.get("kind", "other"), ASSET_KINDS,
                            "product or asset type"),
            "stage": _status(row.get("stage", "unknown"), ASSET_STAGES,
                             "product or asset stage"),
            "public_summary": _text(row.get("public_summary", ""),
                                     "Public description", 3000),
            "public_url": _url(row.get("public_url", ""),
                                "Public description URL"),
            "differentiation_question": _text(
                row.get("differentiation_question", ""),
                "Differentiation research question", 3000),
            "contributors_status": _status(
                row.get("contributors_status", "unknown"),
                ASSET_CONTRIBUTOR_STATUSES, "contributor record status"),
            "contributor_notes": _text(row.get("contributor_notes", ""),
                                        "Contributor record note", 2000),
            "rights_status": _status(row.get("rights_status", "unknown"),
                                      ASSET_RIGHTS_STATUSES,
                                      "rights record status"),
            "rights_notes": _text(row.get("rights_notes", ""),
                                   "Rights record note", 2000),
            "disclosure_status": disclosure_status,
            "first_public_date": disclosure_date,
            "disclosure_notes": _text(row.get("disclosure_notes", ""),
                                       "Disclosure note", 2000),
            "prior_art_status": _status(
                row.get("prior_art_status", "not_started"),
                ASSET_PRIOR_ART_STATUSES, "prior-art research status"),
            "prior_art_notes": _text(row.get("prior_art_notes", ""),
                                      "Prior-art research note", 3000),
            "prior_art_checked_at": _date(row.get("prior_art_checked_at", ""),
                                           "Prior-art research date"),
            "funding_opportunities": normalized_funding_opportunities,
            "references": normalized_references,
        })
    for row in _rows(data, "communications", {
        "opportunity", "date", "direction", "status", "channel",
        "counterparty", "subject", "content", "evidence_links",
    }):
        direction = _status(row.get("direction", "outgoing"),
                            COMMUNICATION_DIRECTIONS, "communication direction")
        status = _status(row.get("status", "draft"), COMMUNICATION_STATUSES,
                         "communication status")
        allowed_statuses = ({"received"} if direction == "incoming"
                             else {"draft", "sent"})
        if status not in allowed_statuses:
            choices = "received" if direction == "incoming" else "draft or sent"
            raise ValueError(f"A {direction} communication can only be marked {choices}.")
        links = row.get("evidence_links", [])
        if not isinstance(links, list) or len(links) > MAX_COMMUNICATION_EVIDENCE_LINKS:
            raise ValueError("Use at most 10 evidence links for each communication.")
        evidence_links = []
        for index, link in enumerate(links, 1):
            link = _object(link, {"source_id", "title", "url", "notes", "checked_at"},
                           f"Communication evidence link {index}")
            source_id = _text(link.get("source_id", ""),
                               "Communication campaign source ID", 32)
            if source_id and source_id not in source_by_id:
                raise ValueError("A communication evidence link points to a campaign source that no longer exists.")
            evidence_links.append({
                "source_id": source_id,
                # Communication links are snapshots: changing the source
                # register must not rewrite what an old draft cited.
                "title": _text(link.get("title", ""), "Evidence link title", 500),
                "url": _url(link.get("url", ""), "Communication evidence URL"),
                "notes": _text(link.get("notes", ""), "Evidence link notes", 5000),
                "checked_at": _date(link.get("checked_at", ""),
                                    "Evidence link checked date"),
            })
        result["communications"].append({
            "opportunity": _reference(row, names, optional=True),
            "date": _date(row.get("date", ""), "Communication date"),
            "direction": direction,
            "status": status,
            "channel": _status(row.get("channel", "email"),
                                COMMUNICATION_CHANNELS, "communication channel"),
            "counterparty": _text(row.get("counterparty", ""),
                                   "Communication contact", 300),
            "subject": _text(row.get("subject", ""), "Communication subject", 1000),
            "content": _text(row.get("content", ""), "Communication content", 20000),
            "evidence_links": evidence_links,
        })
    # Field and row limits bound validation before any combined encoding occurs.
    if text_characters(result) > MAX_TEXT_CHARACTERS:
        raise ValueError("The campaign exceeds 200,000 text characters. "
                         "Split it into smaller campaigns.")
    encoded = json.dumps(result, ensure_ascii=False, allow_nan=False)
    if len(encoded.encode("utf-8")) > MAX_DOCUMENT_BYTES:
        raise ValueError("The campaign exceeds 1 MB. Split it into smaller campaigns.")
    return result


def _check_date_is_current(value: str, today: date) -> bool:
    if not value:
        return False
    checked = date.fromisoformat(value)
    age_days = (today - checked).days
    return 0 <= age_days <= WINDOW_CHECK_MAX_AGE_DAYS


def _supported(row: dict, today: date | None = None,
               sources: list[dict] | None = None) -> bool:
    current = today or date.today()
    if not all(row[key].strip() for key in (
        "evidence", "source_url", "source_quote", "checked_at",
    )) or not _check_date_is_current(row["checked_at"], current):
        return False
    if row.get("source_id") and sources is not None:
        linked = next((source for source in sources
                       if source["id"] == row["source_id"]), None)
        if (linked is None or row["source_url"] != linked["url"]
                or row["checked_at"] != linked["checked_at"]):
            return False
    return True


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
    active_names = {row["name"] for row in document["opportunities"]
                    if row["status"] in ACTIONABLE_OPPORTUNITY_STATES}
    active_rows = [row for row in document["budget"]
                   if not row["opportunity"] or row["opportunity"] in active_names]
    historical_rows = [row for row in document["budget"]
                       if row["opportunity"] and row["opportunity"] not in active_names]
    result = _budget_total(active_rows)
    result["historical"] = _budget_total(historical_rows)
    result["active_items"] = len(active_rows)
    result["historical_items"] = len(historical_rows)
    groups = []
    for opportunity in document["opportunities"]:
        rows = [row for row in document["budget"]
                if row["opportunity"] == opportunity["name"]]
        totals = _budget_total(rows)
        ceiling = opportunity["ceiling"]
        # A known subtotal can already exceed a ceiling even with unknown lines.
        over = (Decimal(totals["known_total"]) > Decimal(ceiling)
                if can_compare_ceiling(opportunity) else None)
        active = opportunity["status"] in ACTIONABLE_OPPORTUNITY_STATES
        groups.append({"opportunity": opportunity["name"], **totals,
                       "status": opportunity["status"], "historical": not active,
                       "ceiling": ceiling, "over_ceiling": over,
                       "ceiling_currency": ceiling_currency(opportunity),
                       "comparison_note": ceiling_comparison_note(opportunity)})
    result["by_opportunity"] = groups
    result["unallocated_items"] = sum(not row["opportunity"]
                                      for row in document["budget"])
    return result


def _readiness(document: dict, metrics: list[dict], budget: dict) -> dict:
    active = [row for row in document["opportunities"]
              if row["status"] in ACTIONABLE_OPPORTUNITY_STATES]
    active_names = {row["name"] for row in active}
    application_windows_to_check = sum(
        not _application_window_is_current(row, date.today(), document["sources"])
        for row in active)
    current_actions = [row for row in document["actions"]
                       if row["status"] == "open"
                       and _action_is_current(row, document["opportunities"])]
    actions_scope_unconfirmed = sum(
        row["status"] == "open" and not row["scope_confirmed"]
        for row in document["actions"])
    actions_submission_phase_review = sum(
        1 for row in document["actions"]
        if row["status"] == "open" and row["scope_confirmed"]
        and row["opportunity"]
        and row["submission_phase"] != "post_submission"
        and any(item["name"] == row["opportunity"]
                and item["status"] == "submitted"
                for item in document["opportunities"]))
    actions_phase_reclassification = sum(
        1 for row in document["actions"]
        if row["status"] == "open" and row["scope_confirmed"]
        and row["opportunity"] and row["submission_phase"] == "post_submission"
        and any(item["name"] == row["opportunity"]
                and item["status"] in ACTIONABLE_OPPORTUNITY_STATES
                for item in document["opportunities"]))
    actions_inactive_route_review = sum(
        1 for row in document["actions"]
        if row["status"] == "open" and row["scope_confirmed"]
        and row["opportunity"]
        and any(item["name"] == row["opportunity"]
                and item["status"] in {"closed", "paused", "not_pursuing"}
                for item in document["opportunities"]))
    checks = [row for row in document["requirements"]
              if row["opportunity"] in active_names]
    sources = document["sources"]
    archived_checks = len(document["requirements"]) - len(checks)
    active_answers = [row for row in document["answers"]
                      if not row["opportunity"] or row["opportunity"] in active_names]
    routes_requiring_answers = [row for row in active
                                if _application_route_confirmed(row)]
    active_by_name = {row["name"]: row for row in active}
    answers_on_unconfirmed_routes = sum(
        bool(row["opportunity"] in active_by_name)
        and not _application_route_confirmed(
            active_by_name[row["opportunity"]])
        for row in active_answers)
    current_answer_indexes = {
        index for index, row in enumerate(document["answers"])
        if not row["opportunity"]
        or (row["opportunity"] in active_by_name
            and _application_route_confirmed(active_by_name[row["opportunity"]]))
    }
    current_answers = [row for index, row in enumerate(document["answers"])
                       if index in current_answer_indexes]
    active_metrics = [metric for metric in metrics
                      if metric["index"] in current_answer_indexes]
    active_budget_rows = [row for row in document["budget"]
                          if not row["opportunity"] or row["opportunity"] in active_names]
    active_budget = _budget_total(active_budget_rows)
    unsupported = sum(row["status"] in {"met", "not_met"}
                      and not _supported(row, date.today(), sources)
                      for row in checks)
    core_missing = [key for key in ("organisation", "objective", "opportunities")
                    if not document[key] or (isinstance(document[key], str)
                                             and not document[key].strip())]
    result = {
        "status": "human_review", "notice": NOTICE,
        "missing_sections": core_missing,
        "requirements_total": len(checks),
        "requirements_archived": archived_checks,
        "requirements_unresolved": sum(
            row["status"] in {"unknown", "clarification"}
            or not _supported(row, date.today(), sources)
            for row in checks),
        "requirements_not_met": sum(row["status"] == "not_met" for row in checks),
        "claims_without_evidence": unsupported,
        "opportunities_without_checks": sum(
            not any(row["opportunity"] == item["name"] for row in checks)
            for item in active),
        "application_workflow_to_confirm": sum(
            row["application_mode"] == "unknown" or (
                row["application_mode"] == "required"
                and not _application_route_confirmed(row))
            for row in active),
        "opportunities_without_sources": sum(not item["url"] for item in active),
        "application_windows_to_check": application_windows_to_check,
        "opportunities_without_answers": sum(
            not any(row["opportunity"] == item["name"]
                    for row in active_answers)
            for item in routes_requiring_answers),
        "answers_on_unconfirmed_application_routes": answers_on_unconfirmed_routes,
        "answers_over_limit": sum(row["over_limit"] for row in active_metrics),
        "answers_empty": sum(not row["text"].strip() for row in current_answers),
        "answers_unreviewed": sum(row["status"] != "reviewed"
                                  for row in current_answers),
        "answer_limits_unknown": sum(row["limit"] is None for row in active_metrics),
        "budget_incomplete": not active_budget["complete"],
        "unknown_costs": active_budget["unknown_costs"],
        "unquoted_costs": active_budget["unquoted_costs"],
        "unallocated_budget_items": sum(not row["opportunity"]
                                         for row in active_budget_rows),
        "budgets_over_ceiling": sum(row["over_ceiling"] is True
                                    for row in budget["by_opportunity"]
                                    if row["opportunity"] in active_names),
        "funding_currency_review": sum(
            bool(row["comparison_note"]) for row in budget["by_opportunity"]
            if row["opportunity"] in active_names),
        "open_actions": len(current_actions),
        "actions_held": sum(row["status"] == "held"
                            for row in document["actions"]),
        "actions_scope_unconfirmed": actions_scope_unconfirmed,
        "actions_submission_phase_review": actions_submission_phase_review,
        "actions_phase_reclassification": actions_phase_reclassification,
        "actions_inactive_route_review": actions_inactive_route_review,
        "actions_to_classify": (actions_scope_unconfirmed
                                 + actions_submission_phase_review
                                 + actions_phase_reclassification
                                 + actions_inactive_route_review),
        "actions_without_owner": sum(
            (
                row["owner_kind"] != "person" or not row["owner_confirmed"])
            for row in current_actions),
    }
    if core_missing or any(value for key, value in result.items()
                           if key not in {"status", "notice", "missing_sections",
                                          "requirements_total", "requirements_archived",
                                          "actions_held"}):
        result["status"] = "needs_attention"
    return result


def _inline(value: str) -> str:
    return literal(" ".join(value.split()))


def _link(url: str, label: str = "Source") -> str:
    # Angle-bracket destinations protect valid URL parentheses in Markdown.
    return f"[{_inline(label)}](<{url}>)" if url else "Source link not recorded"


def _amount(value: str | None) -> str:
    return "Not yet costed" if value is None else "A$" + format(Decimal(value), ",.2f")


def _brief_amount(value: str | None) -> str:
    """Keep the concise decision brief readable without hiding real cents."""
    if value is None:
        return "Not yet costed"
    amount = Decimal(value)
    rendered = (format(amount, ",.0f") if amount == amount.to_integral_value()
                else format(amount, ",.2f"))
    return "A$" + rendered


def _route_amount(row: dict) -> str:
    """Keep a known non-cash route distinct from a missing amount."""
    return funding_amount(row)


def _display_date(value: str) -> str:
    """Render an ISO campaign date for people while keeping audit dates stable."""
    parsed = date.fromisoformat(value)
    month = parsed.strftime("%b")
    if parsed.month == 9:
        month = "Sept"
    return f"{parsed.day} {month} {parsed.year}"


def _application_workflow_description(row: dict) -> str:
    """Describe operator-entered workflow without implying eligibility."""
    if row["application_mode"] == "not_required":
        return "no formal application recorded (user-entered)"
    if row["application_mode"] != "required":
        return "application workflow not confirmed"
    applicant = row["applicant"].strip()
    if not applicant:
        return "formal application required · applicant not recorded"
    if not row["applicant_confirmed"]:
        return ("formal application required · applicant recorded but not "
                "confirmed: " + _inline(applicant))
    return ("formal application required · applicant identity user-confirmed: "
            + _inline(applicant)
            + " (eligibility and signatory authority remain unverified)")


def _application_route_confirmed(row: dict) -> bool:
    return (row["application_mode"] == "required"
            and bool(row["applicant"].strip())
            and row["applicant_confirmed"] is True)


def _answer_hold_reason(row: dict) -> str:
    if row["application_mode"] == "not_required":
        return ("This route is recorded as having no formal application. Saved "
                "answer labels and drafts are held and omitted from this brief.")
    if row["application_mode"] != "required":
        return ("The formal application workflow is not confirmed. Saved answer "
                "labels and drafts are held and omitted from this brief.")
    if not row["applicant"].strip():
        return ("No named applicant is recorded. Saved answer labels and "
                "drafts are held and omitted from this brief.")
    return ("A named applicant is recorded but not directly confirmed. Saved "
            "answer labels and drafts are held and omitted from this brief. Confirm the "
            "named applicant with the person responsible for applying. This "
            "does not establish programme eligibility or authority to submit.")


def _reportable_answer_indexes(document: dict) -> set[int]:
    """Return answer rows safe to include in a shareable campaign report."""
    routes = {row["name"]: row for row in document["opportunities"]}
    return {
        index for index, answer in enumerate(document["answers"])
        if (route := routes.get(answer["opportunity"]))
        and route["status"] in ACTIONABLE_OPPORTUNITY_STATES
        and _application_route_confirmed(route)
    }


def _report_campaign_view(document: dict,
                         reportable_answers: set[int]) -> dict:
    """Keep held and historical answer content out of shareable report data.

    The editable campaign and its explicit JSON backup retain the complete
    labels and drafts. A report view only includes answer rows eligible to
    appear in the active-route brief.
    """
    report = dict(document)
    report["answers"] = []
    for index, row in enumerate(document["answers"]):
        if index in reportable_answers:
            report["answers"].append(dict(row))
        else:
            report["answers"].append({
                **row,
                "label": "Held answer details omitted from report",
                "text": "",
                "limit": None,
            })
    return report


def _application_window_is_current(row: dict, today: date,
                                   sources: list[dict] = ()) -> bool:
    if row["application_window"] not in {"fixed", "rolling"}:
        return False
    if (not row["url"] or not row["window_source_id"]
            or not row["window_source_url"] or not row["window_source_quote"]
            or not row["window_checked_at"]):
        return False
    source = _source_for(sources, row["window_source_id"])
    if (source is None or row["window_source_url"] != source["url"]
            or row["window_checked_at"] != source["checked_at"]):
        return False
    checked = date.fromisoformat(row["window_checked_at"])
    age_days = (today - checked).days
    if age_days < 0 or age_days > WINDOW_CHECK_MAX_AGE_DAYS:
        return False
    return row["application_window"] == "rolling" or bool(row["deadline"]
        and date.fromisoformat(row["deadline"]) >= today)


def _source_for(sources: list[dict], source_id: str) -> dict | None:
    return next((source for source in sources if source["id"] == source_id), None)


def _window_source_notice(row: dict, source: dict | None) -> str:
    if source is None:
        return (" · no registered source linked; link and recheck before use"
                if row["window_source_quote"] else "")
    if (row["window_source_url"] != source["url"]
            or row["window_checked_at"] != source["checked_at"]):
        return (" · saved source snapshot is missing or out of date; "
                "recheck against the linked source before use")
    return ""


def _window_description(row: dict, sources: list[dict] = ()) -> str:
    """Describe the user-entered application window without implying verification."""
    kind = row["application_window"]
    if kind == "rolling":
        label = "Rolling / year-round"
    elif kind == "fixed":
        label = "Fixed closing date: " + (row["deadline"] or "Not recorded")
    else:
        label = "Not checked"
    if row["window_source_quote"]:
        label += ' · wording: “' + _inline(row["window_source_quote"]) + '”'
    source = _source_for(sources, row["window_source_id"])
    if source:
        label += " · linked source: " + (
            _link(source["url"], source["title"])
            if source["url"] else _inline(source["title"]))
        label += " · Source ID " + source["id"][:8]
    label += _window_source_notice(row, source)
    if row["window_checked_at"]:
        checked = date.fromisoformat(row["window_checked_at"])
        age_days = (date.today() - checked).days
        if age_days < 0:
            freshness = " · future-dated check; correct before use"
        elif age_days > WINDOW_CHECK_MAX_AGE_DAYS:
            freshness = (f" · last checked {age_days} days ago; recheck before use")
        else:
            freshness = ""
        label += " · checked: " + row["window_checked_at"] + freshness
    return label + " (user-entered; unverified)"


def _brief_window_description(row: dict, sources: list[dict] = ()) -> str:
    """Format the concise brief for people; retain the ISO audit form elsewhere."""
    kind = row["application_window"]
    if kind == "rolling":
        label = "Rolling / year-round"
    elif kind == "fixed":
        label = "Fixed closing date: " + (
            _display_date(row["deadline"]) if row["deadline"] else "Not recorded")
    else:
        label = "Not checked"
    if row["window_source_quote"]:
        label += ' · wording: “' + _inline(row["window_source_quote"]) + '”'
    source = _source_for(sources, row["window_source_id"])
    if source:
        label += " · linked source: " + (
            _link(source["url"], source["title"])
            if source["url"] else _inline(source["title"]))
        label += " · Source ID " + source["id"][:8]
    label += _window_source_notice(row, source)
    if row["window_checked_at"]:
        checked = date.fromisoformat(row["window_checked_at"])
        age_days = (date.today() - checked).days
        if age_days < 0:
            freshness = " · future-dated check; correct before use"
        elif age_days > WINDOW_CHECK_MAX_AGE_DAYS:
            freshness = (f" · last checked {age_days} days ago; recheck before use")
        else:
            freshness = ""
        label += " · checked: " + _display_date(row["window_checked_at"]) + freshness
    return label + " (user-entered; unverified)"


def _objective_markdown(value: str) -> str:
    """Preserve user paragraph structure and make short lead-ins scannable."""
    paragraphs = re.split(r"\n\s*\n+", value.strip())
    rendered = []
    for paragraph in paragraphs:
        lines = []
        for line in paragraph.splitlines():
            label = re.match(r"^([\w][\w &()’'–—-]{1,38}):[ \t]*(.*)$", line)
            if label:
                lines.append("**" + literal(label.group(1)) + ":** "
                             + literal(label.group(2)))
            else:
                lines.append(literal(line))
        rendered.append("  \n".join(lines))
    return "\n\n".join(rendered)


def _next_open_action(document: dict, focused_opportunity: str) -> dict | None:
    """Select the same route-aware action shown in the campaign decision card."""
    open_actions = [(index, row) for index, row in enumerate(document["actions"])
                    if row["status"] == "open" and row["task"].strip()
                    and _action_is_current(row, document["opportunities"])]

    def by_urgency(rows: list[tuple[int, dict]]) -> dict | None:
        overdue = [(index, row) for index, row in rows
                   if row["due"] and row["due"] < date.today().isoformat()]
        if overdue:
            return min(overdue, key=lambda pair: (pair[1]["due"], pair[0]))[1]
        upcoming = [(index, row) for index, row in rows
                    if row["due"] and row["due"] >= date.today().isoformat()]
        if upcoming:
            return min(upcoming, key=lambda pair: (pair[1]["due"], pair[0]))[1]
        undated = next((row for _, row in rows if not row["due"]), None)
        return undated or (rows[0][1] if rows else None)

    route_actions = [(index, row) for index, row in open_actions
                     if focused_opportunity and row["opportunity"] == focused_opportunity]
    campaign_actions = [(index, row) for index, row in open_actions
                        if not row["opportunity"]]
    other_route_actions = [(index, row) for index, row in open_actions
                           if row["opportunity"]
                           and row["opportunity"] != focused_opportunity]
    return (by_urgency(route_actions) or by_urgency(campaign_actions)
            or by_urgency(other_route_actions))


def _portfolio_summary(assets: list[dict]) -> dict:
    """Summarise open record work without treating it as an IP conclusion."""
    return {
        "assets_total": len(assets),
        "assets_without_funding_routes": sum(
            not row["funding_opportunities"] for row in assets),
        # No field in this register proves legal title or contributor clearance.
        # A recorded reference remains unverified until reviewed outside Sinter.
        "contributor_records_unverified": len(assets),
        "rights_records_unverified": len(assets),
        "disclosure_dates_unknown": sum(not row["first_public_date"]
                                        for row in assets),
        "prior_art_not_started": sum(row["prior_art_status"] == "not_started"
                                      for row in assets),
        "prior_art_leads_recorded": sum(
            row["prior_art_status"] in {"leads_recorded", "preliminary_screen"}
            for row in assets),
        "evidence_references": sum(len(row["references"]) for row in assets),
    }


def _render_portfolio_register(assets: list[dict], sources: list[dict]) -> list[str]:
    if not assets:
        return []
    lines = [
        "## Product and IP research register",
        "Separate from funding eligibility. All classifications, dates, statuses "
        "and references below are campaign entries and have not been independently "
        "verified. A public licence statement is not proof of company title; a "
        "preliminary prior-art screen is not a novelty, patentability or "
        "freedom-to-operate conclusion. No asset-level state in this register "
        "confirms company ownership, contributor clearance or a legal result.",
    ]
    for row in assets:
        lines.extend([
            "### " + _inline(row["name"]),
            "Type: " + ASSET_KIND_LABELS[row["kind"]]
            + " · Stage: " + ASSET_STAGE_LABELS[row["stage"]],
            "Funding routes to assess: "
            + (", ".join(_inline(name) for name in row["funding_opportunities"])
               if row["funding_opportunities"] else "Not linked"),
            "Contributor record: " + ASSET_CONTRIBUTOR_LABELS[row["contributors_status"]]
            + " · Rights record: " + ASSET_RIGHTS_LABELS[row["rights_status"]],
            "First public disclosure: "
            + (row["first_public_date"] or "Not recorded")
            + " · Disclosure record: "
            + ASSET_DISCLOSURE_LABELS[row["disclosure_status"]],
            "Prior-art research: " + ASSET_PRIOR_ART_LABELS[row["prior_art_status"]]
            + (" · Checked: " + row["prior_art_checked_at"]
               if row["prior_art_checked_at"] else ""),
        ])
        if row["public_summary"].strip():
            lines.extend(["Public description (user-entered):",
                          literal(row["public_summary"])])
        if row["public_url"]:
            lines.append("Public description link (user-entered): "
                         + _link(row["public_url"]))
        if row["differentiation_question"].strip():
            lines.extend(["Differentiation research question (not a conclusion):",
                          literal(row["differentiation_question"])])
        for label, value in (
            ("Contributor record note", row["contributor_notes"]),
            ("Rights record note", row["rights_notes"]),
            ("Disclosure record note", row["disclosure_notes"]),
            ("Prior-art research note", row["prior_art_notes"]),
        ):
            if value.strip():
                lines.extend([label + " (user-entered):", literal(value)])
        if row["references"]:
            lines.append("Evidence references (campaign-entered; not opened or checked by Sinter):")
            for reference in row["references"]:
                linked_source = _source_for(sources, reference["source_id"])
                title = _inline(reference["title"])
                url = reference["url"]
                kind = ASSET_REFERENCE_LABELS[reference["kind"]]
                lines.append("- " + kind + ": "
                             + (_link(url, title) if url else title)
                             + (" · Source ID " + reference["source_id"][:8]
                                if linked_source else ""))
                checked_at = reference["checked_at"]
                if checked_at:
                    lines.append("  Checked date (campaign-entered): " + checked_at)
                if linked_source:
                    changed = []
                    if reference["title"] != linked_source["title"]:
                        changed.append("title")
                    if reference["url"] != linked_source["url"]:
                        changed.append("URL")
                    if reference["checked_at"] != linked_source["checked_at"]:
                        changed.append("checked date")
                    if changed:
                        current = _inline(linked_source["title"])
                        if linked_source["url"]:
                            current = _link(linked_source["url"], current)
                        current_date = (linked_source["checked_at"]
                                        or "not recorded")
                        lines.append(
                            "  RECHECK RECOMMENDED — linked source "
                            + ", ".join(changed)
                            + " changed since this evidence snapshot was recorded. "
                            + "Current source register: " + current
                            + " · checked: " + current_date
                            + ". Re-open the saved passage, confirm it still applies, "
                            + "and update this reference before relying on it.")
                if reference["excerpt"].strip():
                    lines.extend(["  Relevant passage (campaign-entered; quote or paraphrase):",
                                  literal(reference["excerpt"])])
                if reference["notes"].strip():
                    lines.append("  " + literal(reference["notes"]))
    return lines


def _render_decision_brief(document: dict, readiness: dict,
                           budget: dict, focused_opportunity: str) -> str:
    """Render a share-reviewable summary without answer or source content."""
    active = [row for row in document["opportunities"]
              if row["status"] in ACTIONABLE_OPPORTUNITY_STATES]
    submitted = [row for row in document["opportunities"]
                 if row["status"] == "submitted"]
    lines = ["# " + _inline(document["title"]),
             "**INTERNAL · REVIEW BEFORE SHARING**",
             "## Current recorded status"]
    if focused_opportunity:
        lines.append("Route in focus: " + _inline(focused_opportunity)
                     + " (selected in Sinter; not an eligibility decision).")
    if not active:
        lines.append("No application route is currently recorded as active.")
    for row in active:
        status = {"not_pursuing": "not pursuing this round"}.get(
            row["status"], row["status"])
        lines.extend([
            "### " + _inline(row["name"]),
            "**Status entered:** " + _inline(status)
            + " · **Funder:** " + _inline(row["funder"] or "Not recorded"),
                      "**Route type (user-entered):** "
                      + row["route_type"].replace("_", " "),
            "**Application workflow (user-entered):** "
            + _application_workflow_description(row),
            "**Application window:** " + _brief_window_description(
                row, document["sources"]),
            "**Cash award / ceiling:** " + _route_amount(row),
        ])
        comparison = ceiling_comparison_note(row)
        if comparison:
            lines.append("**Currency review:** " + comparison)
    if submitted:
        lines.extend(["### Submitted routes",
                      "These user-entered statuses are not independently verified."])
        lines.extend("- **" + _inline(row["name"])
                     + "** — status entered: submitted"
                     for row in submitted)
    lines.append("Statuses, dates and ceilings are campaign entries; Sinter has "
                 "not verified them.")

    unresolved = readiness["requirements_unresolved"]
    check_label = "requirement check" if unresolved == 1 else "requirement checks"
    review_items = [
        f"{unresolved} {check_label} unresolved",
        f"{readiness['requirements_not_met']} marked not met",
        f"{readiness['claims_without_evidence']} marked checks have incomplete or stale evidence",
        f"{readiness['open_actions']} open actions (confirmed current scope only)",
    ]
    if readiness["actions_held"]:
        review_items.append(
            f"{readiness['actions_held']} action(s) on hold by your choice, "
            "retained and not completed; excluded from current work")
    workflow_count = readiness["application_workflow_to_confirm"]
    if workflow_count:
        review_items.append(
            f"{workflow_count} active route(s) need their application process, "
            "named applicant and explicit applicant confirmation recorded")
    missing_answers = readiness["opportunities_without_answers"]
    if missing_answers:
        review_items.append(
            f"{missing_answers} route(s) with a confirmed formal application have no answer drafts")
    unconfirmed_answer_routes = readiness["answers_on_unconfirmed_application_routes"]
    if unconfirmed_answer_routes:
        review_items.append(
            f"{unconfirmed_answer_routes} answer draft(s) are held because their "
            "route application and applicant are unconfirmed")
    unconfirmed_scopes = readiness["actions_scope_unconfirmed"]
    if unconfirmed_scopes:
        review_items.append(
            f"{unconfirmed_scopes} open action(s) need scope confirmation; "
            "they are not current work until classified as campaign-wide or route-specific")
    phase_reviews = readiness["actions_submission_phase_review"]
    if phase_reviews:
        review_items.append(
            f"{phase_reviews} unfinished pre-submission action(s) on submitted route(s) need review; "
            "only a person-marked after-submission follow-up counts as current")
    phase_reclassification = readiness["actions_phase_reclassification"]
    if phase_reclassification:
        review_items.append(
            f"{phase_reclassification} post-submission action(s) on active route(s) need reclassification "
            "before they can return to current work")
    inactive_route_actions = readiness["actions_inactive_route_review"]
    if inactive_route_actions:
        review_items.append(
            f"{inactive_route_actions} open action(s) are held on closed, paused or not-pursued routes; "
            "move continuing work to a current scope or explicitly put it on hold; "
            "mark Done only when completed")
    window_count = readiness["application_windows_to_check"]
    if window_count:
        review_items.append(
            f"{window_count} active application window(s) need current official wording "
            "and a dated check within 90 days")
    if not budget["items"]:
        review_items.append("No costs are linked to active opportunities; the current project total is unknown")
    elif not budget["complete"]:
        count = budget["unknown_costs"]
        cost_label = "cost remains" if count == 1 else "costs remain"
        review_items.append(
            f"{count} {cost_label} unknown; known subtotal {_brief_amount(budget['known_total'])}; total unknown")
    else:
        review_items.append("Recorded cost total: " + _brief_amount(budget["total"]))
    if readiness["funding_currency_review"]:
        review_items.append(
            f"{readiness['funding_currency_review']} active funding ceiling(s) "
            "cannot be compared with AUD project costs; review currencies and "
            "funding terms separately, without an assumed conversion")
    lines.extend(["## Open review items",
                  *["- " + item for item in review_items]])

    next_action = _next_open_action(document, focused_opportunity)
    if next_action:
        owner = _action_owner_summary(next_action["owner"],
                                      next_action["owner_kind"],
                                      next_action["owner_confirmed"])
        route = next((item for item in document["opportunities"]
                      if item["name"] == next_action["opportunity"]), None)
        scope = (_inline(next_action["opportunity"])
                 + (" (submitted route)" if route and route["status"] == "submitted" else "")
                 if next_action["opportunity"] else "Campaign-wide")
        phase = (" · Phase: After-submission follow-up"
                 if next_action["submission_phase"] == "post_submission" else "")
        target = (_display_date(next_action["due"]) + " (proposed, not confirmed)"
                  if next_action["due"] else "not set")
        lines.extend(["## Next recorded open action",
                      "- " + _inline(next_action["task"])
                      + " · Scope: " + scope
                      + phase
                      + " · Owner: " + owner
                      + " · Proposed date: " + target])
    else:
        lines.extend(["## Next recorded open action",
                      ("No current open action is recorded. Review held tasks above before treating them as current."
                       if readiness["actions_to_classify"] else
                       "No current open action is recorded.")])

    if document["assets"]:
        portfolio = _portfolio_summary(document["assets"])
        lines.extend([
            "## Portfolio IP workstream · separate from funding eligibility",
            f"{portfolio['assets_total']} assets recorded · "
            f"{portfolio['rights_records_unverified']} rights records unverified · "
            f"{portfolio['contributor_records_unverified']} contributor records unverified · "
            f"{portfolio['prior_art_not_started']} prior-art screens not started · "
            f"{portfolio['disclosure_dates_unknown']} disclosure dates unknown · "
            f"{portfolio['assets_without_funding_routes']} assets not linked to a funding route.",
            "These are planning records. Public pages and preliminary searches do "
            "not establish ownership, novelty, patentability or freedom to operate.",
        ])
        for asset in document["assets"]:
            lines.append(
                "- " + _inline(asset["name"])
                + " · Rights: " + ASSET_RIGHTS_LABELS[asset["rights_status"]]
                + " · Prior art: " + ASSET_PRIOR_ART_LABELS[asset["prior_art_status"]]
                + " · First public date: "
                + (asset["first_public_date"] or "Not recorded"))

    lines.extend(["## Review notice", NOTICE])
    return "\n\n".join(lines) + "\n"


def _render(document: dict, readiness: dict, metrics: list[dict],
            budget: dict) -> str:
    lines = ["# " + _inline(document["title"])]
    if document["organisation"]:
        lines.append(_inline(document["organisation"]))
    if document["objective"].strip():
        lines.extend(["## Project objective",
                      _objective_markdown(document["objective"])])
    if not budget["items"]:
        budget_progress = "current project budget not entered; total unknown"
    elif not budget["complete"]:
        budget_progress = "current project total incomplete"
    else:
        budget_progress = f"{readiness['unquoted_costs']} budget items without quotes"
    lines.extend(["## Work still to complete",
                  f"{readiness['requirements_unresolved']} requirements unresolved; "
                  f"{readiness['requirements_not_met']} marked not met; "
                  f"{readiness['application_workflow_to_confirm']} routes need workflow or applicant confirmation; "
                  f"{readiness['answers_over_limit']} answers over their limits; "
                  f"{budget_progress}; "
                  f"{readiness['open_actions']} open actions (confirmed current scope only).", NOTICE])
    if readiness["funding_currency_review"]:
        lines.append(
            f"{readiness['funding_currency_review']} active funding ceiling(s) "
            "have a different, unconfirmed or unsupported currency. Project "
            "costs remain AUD; no currency conversion or ceiling comparison "
            "was made for those routes.")
    if readiness["requirements_archived"]:
        count = readiness["requirements_archived"]
        noun, verb, route = ("check is", "does", "opportunity") if count == 1 else ("checks are", "do", "opportunities")
        lines.append(f"{count} {noun} retained for paused, not-pursued, submitted or closed {route} and {verb} not block the current screen.")
    if readiness["missing_sections"]:
        lines.append("Add: " + ", ".join(readiness["missing_sections"]) + ".")
    if readiness["claims_without_evidence"]:
        lines.append(f"{readiness['claims_without_evidence']} marked checks need "
                     "applicant evidence, source wording, a source link "
                     "or a current date checked.")
    if readiness["opportunities_without_checks"]:
        lines.append(f"{readiness['opportunities_without_checks']} opportunities have "
                     "no recorded requirements yet.")
    if readiness["actions_without_owner"]:
        lines.append(f"{readiness['actions_without_owner']} open actions have no user-confirmed owner; "
                     "names and role suggestions without recorded acceptance remain unconfirmed.")
    if readiness["actions_held"]:
        lines.append(f"{readiness['actions_held']} action(s) are on hold by your "
                     "choice, retained and not completed. They do not count as "
                     "current work; choose To do explicitly to resume.")
    if readiness["actions_scope_unconfirmed"]:
        count = readiness["actions_scope_unconfirmed"]
        lines.append(f"{count} open action(s) need scope confirmation and do not count as current work until classified.")
    if readiness["actions_submission_phase_review"]:
        count = readiness["actions_submission_phase_review"]
        lines.append(f"{count} unfinished pre-submission action(s) on submitted route(s) need review; only after-submission follow-ups count as current.")
    if readiness["actions_phase_reclassification"]:
        count = readiness["actions_phase_reclassification"]
        lines.append(f"{count} post-submission action(s) on active route(s) need reclassification before returning to current work.")
    if readiness["actions_inactive_route_review"]:
        count = readiness["actions_inactive_route_review"]
        lines.append(f"{count} open action(s) belong to closed, paused or not-pursued routes; move continuing work to a current scope or explicitly put it on hold. Mark Done only when completed.")
    for item in document["opportunities"]:
        name = item["name"]
        active = item["status"] in ACTIONABLE_OPPORTUNITY_STATES
        status_label = {"not_pursuing": "not pursuing this round"}.get(
            item["status"], item["status"])
        lines.extend(["## " + _inline(name),
                      "Funder: " + _inline(item["funder"] or "Not recorded")
                      + " · Campaign status entered: " + status_label,
                      "Route type (user-entered): "
                      + item["route_type"].replace("_", " "),
                      "Application workflow (user-entered): "
                      + _application_workflow_description(item),
                      "Application window: " + _window_description(
                          item, document["sources"])
                      + " · Cash award / ceiling: " + _route_amount(item),
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
            label = {"met": "User-marked met · unverified",
                     "not_met": "User-marked not met · unverified",
                     "unknown": "User-entered status · not checked",
                     "clarification": "User-entered status · clarification needed"}
            state = label[row["status"]]
            if not active:
                state = "Historical record · " + state
            if row["status"] in {"met", "not_met"} and not _supported(
                    row, sources=document["sources"]):
                state += " — source record incomplete or stale"
            evidence = literal(row["evidence"] or "Not recorded")
            wording = literal(row["source_quote"] or "Not recorded")
            linked_source = _source_for(document["sources"], row["source_id"])
            source_link = _link(
                row["source_url"],
                linked_source["title"] if linked_source else
                "User-entered source link; not checked by Sinter")
            if linked_source:
                source_link += " · Source ID " + linked_source["id"][:8]
                if (row["source_url"] != linked_source["url"]
                        or row["checked_at"] != linked_source["checked_at"]):
                    source_link += (" · linked source record changed after this excerpt; "
                                    "recheck before use")
            checked_at = row["checked_at"] or "Not recorded"
            lines.extend([
                "**" + state + ":** " + literal(row["rule"]),
                "Applicant evidence (user-entered; unverified): " + evidence,
                "Source wording (user-entered; unverified): " + wording,
                source_link + " · Date checked (user-entered): " + checked_at,
            ])
        indexes = [index for index, row in enumerate(document["answers"])
                   if row["opportunity"] == name]
        if not active:
            lines.extend([
                "### Historical answer drafts · inactive route",
                "These superseded drafts may contain unconfirmed assumptions and are not for submission. Their presence does not show whether anything was submitted; verify the original portal record separately.",
            ])
            if not indexes:
                lines.append("No historical answer drafts have been retained.")
            else:
                lines.append(
                    f"{len(indexes)} historical answer row(s) retained; "
                    "question labels and text omitted from this report.")
        else:
            lines.append("### Application answers")
            if not indexes:
                lines.append("No application answers have been recorded yet.")
        if active and not _application_route_confirmed(item):
            lines.append(_answer_hold_reason(item))
            if indexes:
                lines.append(
                    f"{len(indexes)} retained answer row(s); labels and text omitted.")
        elif active:
            for index in indexes:
                row, count = document["answers"][index], metrics[index]
                limit = ("limit not recorded" if count["limit"] is None
                         else f"limit {count['limit']}")
                details = (f"{count['characters']} characters · "
                           f"{count['words']} words · "
                           f"{limit} · {row['status']}"
                           + (" · OVER LIMIT" if count["over_limit"] else ""))
                lines.extend(["#### " + _inline(row["label"]), details])
                lines.append(literal(row["text"]) if row["text"].strip()
                             else "Answer not drafted yet.")
    active_names = {row["name"] for row in document["opportunities"]
                    if row["status"] in ACTIONABLE_OPPORTUNITY_STATES}
    active_budget_rows = [row for row in document["budget"]
                          if not row["opportunity"] or row["opportunity"] in active_names]
    historical_budget_rows = [row for row in document["budget"]
                              if row["opportunity"] and row["opportunity"] not in active_names]
    lines.append("## Current project budget")
    if not active_budget_rows:
        lines.append("No budget items are recorded for active opportunities. "
                     "The project total is unknown.")
    else:
        lines.extend(["| Item | Opportunity | Quantity | Unit cost | Line total "
                      "| Quote |",
                      "| --- | --- | ---: | ---: | ---: | --- |"])
        for row in active_budget_rows:
            total = (None if row["unit_cost"] is None else
                     str(Decimal(row["unit_cost"]) * row["quantity"]))
            cells = [_inline(row["item"]), _inline(row["opportunity"] or "Unallocated"),
                     str(row["quantity"]), _amount(row["unit_cost"]), _amount(total),
                     _inline(row["quote_reference"] or "Quote needed")]
            lines.append("| " + " | ".join(cells) + " |")
        if budget["complete"]:
            lines.append("**Current entered cost: " + _amount(budget["total"]) + "**")
        else:
            lines.append("**Known subtotal: " + _amount(budget["known_total"])
                         + f". Total incomplete: {budget['unknown_costs']} items "
                         "still need costs.**")
        for group in budget["by_opportunity"]:
            if group["items"] and group["opportunity"] in active_names:
                lines.append(_inline(group["opportunity"]) + ": "
                             + _amount(group["known_total"])
                             + (" known subtotal" if not group["complete"]
                                else " allocated")
                             + (" — exceeds the entered funding ceiling."
                                if group["over_ceiling"] else "."))
                if group["comparison_note"]:
                    lines.append(_inline(group["opportunity"]) + ": "
                                 + group["comparison_note"])
    if historical_budget_rows:
        lines.extend(["### Historical budget items · inactive routes",
                      "These costs belong to closed, submitted, paused or not-pursued routes. They are excluded from the current project total and readiness checks.",
                      "| Item | Opportunity | Quantity | Unit cost | Line total | Quote |",
                      "| --- | --- | ---: | ---: | ---: | --- |"])
        for row in historical_budget_rows:
            total = (None if row["unit_cost"] is None else
                     str(Decimal(row["unit_cost"]) * row["quantity"]))
            cells = [_inline(row["item"]), _inline(row["opportunity"]),
                     str(row["quantity"]), _amount(row["unit_cost"]), _amount(total),
                     _inline(row["quote_reference"] or "Quote needed")]
            lines.append("| " + " | ".join(cells) + " |")
        historical = budget["historical"]
        if historical["complete"]:
            lines.append("**Historical known subtotal (excluded above): "
                         + _amount(historical["total"]) + "**")
        else:
            lines.append("**Historical known subtotal (excluded above): "
                         + _amount(historical["known_total"])
                         + f" · {historical['unknown_costs']} historical items remain uncosted.**")
    lines.append("## Next actions")
    if not document["actions"]:
        lines.append("No actions have been recorded yet.")
    for row in document["actions"]:
        owner = _action_owner_summary(row["owner"], row["owner_kind"],
                                      row["owner_confirmed"])
        target = (row["due"] + " · proposed target, not confirmed"
                  if row["due"] else "not set")
        scope = ("Not confirmed" if not row["scope_confirmed"] else
                 _inline(row["opportunity"]) if row["opportunity"] else
                 "Campaign-wide")
        phase = (" · Phase: " + ("After-submission follow-up"
                                 if row["submission_phase"] == "post_submission"
                                 else "Before submission")
                 if row["scope_confirmed"] else "")
        lines.append("- " + _inline(row["task"]) + " · Scope: " + scope + phase
                     + " · Owner: " + owner
                     + " · Proposed target: " + target + " · "
                     + ("On hold · retained, not completed"
                        if row["status"] == "held" else row["status"]))
    lines.extend(_render_portfolio_register(document["assets"], document["sources"]))
    if document["communications"]:
        lines.extend([
            "## Communications log · user-entered, unverified",
            "These entries are records supplied by you. Sinter did not send, "
            "receive, open or independently verify any communication or link. "
            "A draft is not sent.",
            "This report includes message text and may include personal information. "
            "Review it before sharing; use the redacted evidence-pack export for "
            "external review.",
        ])
        for row in document["communications"]:
            direction = "Incoming" if row["direction"] == "incoming" else "Outgoing"
            status = {"draft": "DRAFT · NOT SENT",
                      "received": "RECORDED AS RECEIVED · UNVERIFIED",
                      "sent": "RECORDED AS SENT · UNVERIFIED"}[row["status"]]
            channel = row["channel"].replace("_", " ").title()
            heading = " · ".join((direction, channel, status))
            lines.append("### " + _inline(heading))
            lines.append("Communication date (user-entered): "
                         + (row["date"] or "Not recorded"))
            if row["opportunity"]:
                lines.append("Opportunity (user-entered): "
                             + _inline(row["opportunity"]))
            if row["counterparty"]:
                lines.append("Other party (user-entered): "
                             + _inline(row["counterparty"]))
            if row["subject"]:
                lines.append("Subject (user-entered): " + _inline(row["subject"]))
            lines.append("Message content or summary (user-entered):")
            lines.append(literal(row["content"]) if row["content"].strip()
                         else "No message text or summary recorded.")
            if row["evidence_links"]:
                lines.append("Evidence links (user-entered; not opened or checked by Sinter):")
                for link in row["evidence_links"]:
                    label = link["title"].strip() or "Open evidence link"
                    lines.append("- " + _link(link["url"], label))
                    if link["source_id"]:
                        lines.append("  Campaign source ID: "
                                     + link["source_id"][:8]
                                     + " · linked source (user-entered)")
                        current_source = _source_for(document["sources"], link["source_id"])
                        if current_source and (
                                link["title"] != current_source["title"]
                                or link["url"] != current_source["url"]
                                or link["checked_at"] != current_source["checked_at"]):
                            lines.append("  Saved source snapshot differs from the current "
                                         "source register; recheck before reuse.")
                    if link["checked_at"]:
                        lines.append("  Linked source check date (campaign-entered): "
                                     + link["checked_at"])
                    if link["notes"].strip():
                        lines.append("  " + literal(link["notes"]))
    if document["sources"]:
        lines.append("## Source references")
        for row in document["sources"]:
            lines.append("### " + _inline(row["title"]))
            lines.append("Source ID: " + row["id"][:8] + " · " + _link(row["url"]))
            lines.append("Date checked (campaign-entered): "
                         + (row["checked_at"] or "Not recorded"))
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


def prepare(data: object, focused_opportunity_name: object = "") -> dict:
    """Prepare a readable campaign pack and derived checks without network access."""
    campaign = validate(data)
    if not isinstance(focused_opportunity_name, str):
        raise ValueError("The focused opportunity must be text.")
    active = [row for row in campaign["opportunities"]
              if row["status"] in ACTIONABLE_OPPORTUNITY_STATES]
    requested_focus = focused_opportunity_name.strip()
    focused_opportunity = next(
        (row["name"] for row in active if row["name"] == requested_focus),
        active[0]["name"] if active else "",
    )
    metrics = _answer_metrics(campaign["answers"])
    budget = _budget_summary(campaign)
    readiness = _readiness(campaign, metrics, budget)
    portfolio = _portfolio_summary(campaign["assets"])
    markdown = _render(campaign, readiness, metrics, budget)
    document_markdown = _render_decision_brief(
        campaign, readiness, budget, focused_opportunity)
    reportable_answers = _reportable_answer_indexes(campaign)
    report_campaign = _report_campaign_view(campaign, reportable_answers)
    report_metrics = [metric for metric in metrics
                      if metric["index"] in reportable_answers]
    return {"workflow": "campaign", "title": campaign["title"],
            "document_title": campaign["title"], "created_at": utc_now(),
            "review_status": "user_entered", "campaign": report_campaign,
            "readiness": readiness, "answer_metrics": report_metrics,
            "budget_summary": budget, "portfolio_summary": portfolio,
            "document_markdown": document_markdown,
            "markdown": markdown}


def saved_report_view(report: object) -> object:
    """Return a privacy-safe view of a campaign report saved by older Sinter.

    Older reports embed the full campaign and rendered answers. Rebuild their
    derived fields through the current report policy at read time, leaving the
    original local report untouched. The campaign remains the editable source
    of truth in Campaigns.
    """
    if not isinstance(report, dict) or report.get("workflow") != "campaign":
        return report

    title = report.get("title") if isinstance(report.get("title"), str) else "Saved campaign"
    refresh_notice = (
        "This older campaign report could not be safely refreshed. Its campaign "
        "content is omitted from this view. Open the saved campaign in Campaigns "
        "and prepare a new report.")
    try:
        source_campaign = validate(report.get("campaign"))
        focused = ""
        document_markdown = report.get("document_markdown", "")
        if isinstance(document_markdown, str):
            focus_prefix = "Route in focus: "
            focus_line = next((line for line in document_markdown.splitlines()
                               if line.startswith(focus_prefix)), "")
            entered_focus = focus_line[len(focus_prefix):].split(
                " (selected in Sinter", 1)[0]
            focused = next((row["name"] for row in source_campaign["opportunities"]
                            if _inline(row["name"]) == entered_focus), "")
        safe_report = prepare(source_campaign, focused)

        reportable = _reportable_answer_indexes(source_campaign)
        has_held_answers = any(index not in reportable
                               for index in range(len(source_campaign["answers"])))

        # Keep stable report metadata, but only expose fields whose contents
        # are regenerated or explicitly safe. Future unrecognized fields must
        # not accidentally become another copy of an answer.
        view = {
            "workflow": "campaign",
            "title": title,
            "document_title": (report.get("document_title")
                               if isinstance(report.get("document_title"), str)
                               else safe_report["document_title"]),
            "created_at": report.get("created_at", safe_report["created_at"]),
            "review_status": "user_entered",
            "campaign": safe_report["campaign"],
            "readiness": safe_report["readiness"],
            "answer_metrics": safe_report["answer_metrics"],
            "budget_summary": safe_report["budget_summary"],
            "portfolio_summary": safe_report["portfolio_summary"],
            "document_markdown": safe_report["document_markdown"],
            "markdown": safe_report["markdown"],
        }
        edits = report.get("document_edits")
        if isinstance(edits, dict) and isinstance(edits.get("markdown"), str):
            edited_at = edits.get("edited_at", "")
            author = edits.get("author", "user")
            if not isinstance(edited_at, str):
                edited_at = ""
            if not isinstance(author, str):
                author = "user"
            if has_held_answers:
                edit_markdown = (
                    "[This older edited brief is omitted from the report view "
                    "because it may include application answers held from this "
                    "report. Your saved campaign remains available in Campaigns; "
                    "confirm the route and applicant before preparing a new brief.]")
            else:
                edit_markdown = edits["markdown"]
            # Project only the known edit fields. Older or future versions may
            # attach other payloads here, which must not bypass report filtering.
            view["document_edits"] = {
                "markdown": edit_markdown,
                "edited_at": edited_at[:100],
                "author": author[:120],
            }
            if has_held_answers:
                view["document_edits"]["redacted_for_report_view"] = True
        return view
    except Exception:
        # Malformed old payloads fail closed rather than being returned raw.
        return {
            "workflow": "campaign",
            "title": title,
            "document_title": title,
            "created_at": report.get("created_at", ""),
            "review_status": "needs_refresh",
            "campaign": None,
            "readiness": {},
            "answer_metrics": [],
            "budget_summary": {},
            "portfolio_summary": {},
            "document_markdown": "# Campaign report needs refresh\n\n" + refresh_notice,
            "markdown": "# Campaign report needs refresh\n\n" + refresh_notice,
            "warnings": [refresh_notice],
        }


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

    @staticmethod
    def _next_updated_at(db: sqlite3.Connection) -> str:
        """Order successful saves inside the existing serialized write transaction."""
        now = datetime.fromisoformat(utc_now())
        latest = db.execute("SELECT MAX(updated_at) FROM campaigns").fetchone()[0]
        if latest:
            # Existing stores use second-resolution UTC stamps. Keep those rows
            # intact; ties or a clock rollback must not reopen an older campaign.
            now = max(now, datetime.fromisoformat(latest) + timedelta(microseconds=1))
        return now.isoformat(timespec="microseconds")

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
                db.execute(
                    "INSERT INTO campaigns VALUES (?,?,?,?,?)",
                    (id, revision, normalized["title"], self._next_updated_at(db), encoded),
                )
            else:
                cursor = db.execute(
                    "UPDATE campaigns SET revision=revision+1,title=?,updated_at=?,"
                    "document=? WHERE id=? AND revision=?",
                    (normalized["title"], self._next_updated_at(db), encoded, id, revision),
                )
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
                # Normalize older v1 documents on read. Missing additive fields
                # default safely without requiring a database rewrite.
                "document": validate(json.loads(row["document"]))}

    def delete(self, id: str, revision: int) -> None:
        """Remove only the revision reviewed by the caller."""
        id, revision = self._identifier(id), self._revision(revision)
        with self._connect() as db:
            cursor = db.execute("DELETE FROM campaigns WHERE id=? AND revision=?",
                                (id, revision))
            if cursor.rowcount != 1:
                raise ValueError("This campaign changed or was removed. "
                                 "Reopen it before deleting.")
