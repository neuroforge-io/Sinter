"""Exact current-campaign funding arithmetic over explicitly normalized records.

This is a recorded assessment, never an eligibility decision, submission,
award verification, exchange conversion, lifetime ledger or spending authority.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from decimal import Context, Decimal, localcontext

from .campaign_currency import ceiling_currency
from .evidence import literal

SCHEMA = "sinter-funding-summary/v1"
STAGES = ("available", "targets", "submitted", "awarded", "received", "closed")
NOTE = (
    "Recorded totals cover this campaign only, not audited lifetime funding. "
    "Available amounts are individual ceilings supported by entered eligibility "
    "and current source checks; they are not awards or guaranteed cash. "
    "Targets, submitted requests, awards and receipts are separate stages; do "
    "not add them together. Credits are nominal service credits, not cash. "
    "Amounts are cumulative entered amounts for one round, benefit type and "
    "currency, not individual payments. Evidence is retained for review, not "
    "independently verified. One benefit type per round is supported; mixed "
    "cash-and-credit rounds require reconciliation and are not combined. "
    "No currency conversion is made. Unknowns and excluded records remain "
    "explicit; an empty stage does not prove no historical funding."
)
REASONS = {
    "missing_round_key": "Funding round identity is not recorded",
    "duplicate_round": "Duplicate round records need reconciliation",
    "benefit_unclassified": "Cash versus credits is unconfirmed",
    "unsupported_benefit": "Equity, tax relief or matched research support is outside these totals",
    "currency_unconfirmed": "Currency is unconfirmed or unsupported",
    "eligibility_unconfirmed": "Eligibility is not recorded as eligible",
    "ineligible": "Entered eligibility assessment is ineligible",
    "eligibility_evidence_missing": "Eligibility evidence is incomplete, stale or inconsistent",
    "ceiling_not_individual": "Individual award ceiling is not confirmed",
    "ceiling_evidence_missing": "Individual ceiling evidence is incomplete, stale or inconsistent",
    "window_unconfirmed": "Application window is not current and supported",
    "status_conflict": "Funding event contradicts the recorded route status",
    "state_unconfirmed": "Entered amount is retained but its funding event is unconfirmed",
    "inactive_stage": "Entered amount is retained but its funding event is not recorded for this stage",
    "receipt_conflict": "Receipt is recorded alongside an explicit not-awarded status; reconcile these records",
}


def _round_key(row):
    # Deliberately explicit: funder URLs/names alone cannot identify a round.
    return " ".join(row.get("funding_tracking", {}).get("round_key", "").split()).casefold()


def _application(row):
    tracking = row.get("funding_tracking", {})
    recorded = tracking.get("application_status", "unknown")
    if row["status"] == "submitted" and recorded not in {"unknown", "submitted"}:
        return "conflicting"
    if recorded == "submitted" and row["status"] in {"researching", "open", "upcoming", "clarification"}:
        return "conflicting"
    return "submitted" if recorded == "unknown" and row["status"] == "submitted" else recorded


def _receipt(row):
    tracking = row.get("funding_tracking", {})
    state = tracking.get("receipt_status", "unknown")
    if state == "received" and tracking.get("award_status") == "not_awarded":
        return "conflicting"
    return state


def summarize(campaign, as_of, current_windows, current_claims):
    """Pure totals; no caller-owned input is mutated or normalized here."""
    rows = campaign["opportunities"]
    rounds = defaultdict(list)
    for row in rows:
        if key := _round_key(row):
            rounds[key].append(row["name"])
    duplicates = {key: names for key, names in rounds.items() if len(names) > 1}
    entities = defaultdict(list)
    for index, row in enumerate(rows):
        entities[_round_key(row) or ("unidentified", index)].append(row)

    def entity_counts(field):
        counts = Counter()
        for members in entities.values():
            values = {
                _application(row) if field == "application_status"
                else _receipt(row) if field == "receipt_status"
                else row.get("funding_tracking", {}).get(field, "unknown")
                for row in members
            }
            counts[next(iter(values)) if len(values) == 1 else "conflicting"] += 1
        return dict(sorted(counts.items()))

    counts = {
        "opportunities": len(rows),
        "identified_rounds": len(rounds),
        "missing_round_keys": sum(not _round_key(row) for row in rows),
        "duplicate_rounds": len(duplicates),
        "duplicate_rows": sum(len(names) - 1 for names in duplicates.values()),
        "by_status": dict(sorted(Counter(row["status"] for row in rows).items())),
        "applications": entity_counts("application_status"),
        "awards": entity_counts("award_status"),
        "receipts": entity_counts("receipt_status"),
        "closed_outcomes": {},
    }
    stages = {stage: {"opportunities": 0, "groups": [], "excluded_rows": 0}
              for stage in STAGES}
    stage_entities = {stage: set() for stage in STAGES}
    groups = {stage: {} for stage in STAGES}
    exclusions = []
    closed_entities = defaultdict(set)

    def exclude(row, stage, reason):
        exclusions.append({"opportunity": row["name"], "stage": stage,
                           "reason": reason, "message": REASONS[reason]})
        stages[stage]["excluded_rows"] += 1

    def add(row, stage, amount, currency, conflict=""):
        tracking = row.get("funding_tracking", {})
        kind = tracking.get("benefit_type", "unknown")
        key = _round_key(row)
        stage_entities[stage].add(key or ("unidentified", row["name"]))
        group = groups[stage].setdefault((kind, currency), {
            "benefit_type": kind, "currency": currency,
            "known_total": "0.00", "total": None, "known_amounts": 0,
            "unknown_amounts": 0, "excluded_amounts": 0,
        })
        if amount is None:
            group["unknown_amounts"] += 1
        reason = (
            conflict if conflict else
            "status_conflict" if stage in {"submitted", "closed"} and _application(row) == "conflicting" else
            "missing_round_key" if not key else
            "duplicate_round" if key in duplicates else
            "benefit_unclassified" if kind not in {"cash", "credits"} else
            "unsupported_benefit" if row["route_type"] in {"equity", "tax_incentive", "matched_voucher"}
                or (kind == "cash" and row["route_type"] == "non_cash_support") else
            "currency_unconfirmed" if currency in {"unconfirmed", "other"} else
            ""
        )
        if reason:
            group["excluded_amounts"] += 1
            exclude(row, stage, reason)
            if currency in {"unconfirmed", "other"}:
                group["known_total"] = None
            return
        if amount is None:
            return
        # Admission bounds 200 amounts <= 1e9. Local precision keeps this exact
        # independently of a caller's ambient Decimal context.
        with localcontext(Context(prec=20)):
            group["known_total"] = format(Decimal(group["known_total"]) + Decimal(amount), ".2f")
        group["known_amounts"] += 1

    for row in rows:
        tracking = row.get("funding_tracking", {})
        application = _application(row)
        closed = row["status"] in {"closed", "not_pursuing"} or tracking.get("closure_reason", "unknown") != "unknown"
        if closed:
            key = _round_key(row) or ("unidentified", row["name"])
            reason = tracking.get("closure_reason", "unknown")
            closed_entities[key].add(reason)
            stage_entities["closed"].add(key)
        # Availability is assessed independently from a draft request. Closing a
        # round does not erase its submission, award or received history.
        if row["status"] == "open":
            reason = (
                "status_conflict" if application in {"submitted", "conflicting"} or closed else
                "ineligible" if tracking.get("eligibility") == "ineligible" else
                "eligibility_unconfirmed" if tracking.get("eligibility") != "eligible" else
                "eligibility_evidence_missing" if not current_claims[row["name"]]["eligibility_evidence"] else
                "ceiling_not_individual" if tracking.get("ceiling_scope") != "individual" else
                "ceiling_evidence_missing" if not current_claims[row["name"]]["ceiling_evidence"] else
                "window_unconfirmed" if not current_windows[row["name"]] else ""
            )
            if reason:
                exclude(row, "available", reason)
            else:
                add(row, "available", row["ceiling"], ceiling_currency(row))
        if application == "preparing" and not closed:
            record = tracking.get("target", {})
            add(row, "targets", record.get("amount"), record.get("currency", "unconfirmed"))
        elif tracking.get("target", {}).get("amount") is not None:
            exclude(row, "targets", "state_unconfirmed" if application == "unknown" else "inactive_stage")
        if application in {"submitted", "conflicting"}:
            record = tracking.get("requested", {})
            add(row, "submitted", record.get("amount"), record.get("currency", "unconfirmed"))
            if closed:
                add(row, "closed", record.get("amount"), record.get("currency", "unconfirmed"))
        elif tracking.get("requested", {}).get("amount") is not None:
            reason = "state_unconfirmed" if application == "unknown" else "inactive_stage"
            exclude(row, "submitted", reason)
            if closed:
                exclude(row, "closed", reason)
        for stage, state in (("awarded", "award_status"), ("received", "receipt_status")):
            record = tracking.get(stage, {})
            if tracking.get(state) == ("awarded" if stage == "awarded" else "received"):
                conflict = "receipt_conflict" if stage == "received" and _receipt(row) == "conflicting" else ""
                add(row, stage, record.get("amount"), record.get("currency", "unconfirmed"), conflict)
            elif record.get("amount") is not None:
                exclude(row, stage, "state_unconfirmed" if tracking.get(state) == "unknown" else "inactive_stage")

    closed_counts = Counter(next(iter(reasons)) if len(reasons) == 1 else "conflicting"
                            for reasons in closed_entities.values())
    counts["closed_outcomes"] = dict(sorted(closed_counts.items()))
    for stage in STAGES:
        stages[stage]["opportunities"] = len(stage_entities[stage])
        for _, group in sorted(groups[stage].items()):
            if not group["known_amounts"]:
                group["known_total"] = None
            if not group["unknown_amounts"] and not group["excluded_amounts"]:
                group["total"] = group["known_total"]
            stages[stage]["groups"].append(group)
    result = {
        "schema": SCHEMA, "as_of": as_of, "scope": "current_campaign",
        "notice": NOTE, "counts": counts, "stages": stages,
        "duplicate_rounds": [{"round_key": key, "opportunities": names}
                             for key, names in sorted(duplicates.items())],
        "exclusions": exclusions,
        "amount_basis": {
            "available": "Individual ceilings for recorded eligible open routes with current source checks",
            "targets": "Draft targets for preparing applications",
            "submitted": "Actual requested amounts of recorded submitted applications",
            "awarded": "Amounts of explicitly recorded awards",
            "received": "Amounts of explicitly recorded receipts",
            "closed": "Requested amounts of closed submitted applications; never historical ceilings",
        },
    }
    result["markdown"] = render(result)
    return result


def render(summary):
    """Human CLI/report presentation over the same computed JSON."""
    lines = ["## Recorded funding totals", "", summary["notice"], "",
             f"As of {summary['as_of']}: {summary['counts']['opportunities']} opportunity records; "
             f"{summary['counts']['identified_rounds']} identified rounds.", ""]
    outcomes = summary["counts"]["closed_outcomes"]
    if outcomes:
        lines.extend(["Closed outcomes: " + "; ".join(
            f"{reason.replace('_', ' ')}: {count}" for reason, count in outcomes.items()
        ) + ".", ""])
    for stage, bucket in summary["stages"].items():
        lines.extend([f"### {stage.title()} ({bucket['opportunities']} opportunities)",
                      summary["amount_basis"][stage]])
        if not bucket["groups"]:
            lines.append("No qualified amount records; historical amounts may be unknown.")
        for group in bucket["groups"]:
            known = group["known_total"]
            lines.append(
                f"- {group['currency']} {group['benefit_type']}: "
                + (f"known subtotal {known}" if known is not None else "no qualified subtotal")
                + f"; {group['unknown_amounts']} unknown amounts; "
                + f"{group['excluded_amounts']} excluded amounts."
            )
        if bucket["excluded_rows"]:
            lines.append(f"{bucket['excluded_rows']} records excluded; review reasons below.")
        lines.append("")
    if summary["counts"]["missing_round_keys"]:
        lines.extend([f"{summary['counts']['missing_round_keys']} records lack a round key; "
                      "their amounts are excluded until identified.", ""])
    for duplicate in summary["duplicate_rounds"]:
        lines.append("Duplicate round excluded: " + literal(duplicate["round_key"])
                     + " (" + ", ".join(literal(name) for name in duplicate["opportunities"]) + ").")
    for row in summary["exclusions"]:
        lines.append("- " + literal(row["opportunity"]) + " / " + row["stage"] + ": " + row["message"] + ".")
    return "\n".join(lines).strip() + "\n"
