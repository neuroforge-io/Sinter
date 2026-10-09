"""Pure recorded-cost arithmetic, separate from application budget decisions.

Inputs are normalized campaign/v1 rows. Free-text quote references are retained
by the caller; they cannot qualify GST treatment or eligible application costs.
"""

from __future__ import annotations

from collections.abc import Collection
from decimal import (
    ROUND_HALF_EVEN,
    Context,
    Decimal,
    DivisionByZero,
    Inexact,
    InvalidOperation,
    Overflow,
    Rounded,
    localcontext,
)

from .campaign_currency import (
    can_compare_ceiling,
    ceiling_comparison_note,
    ceiling_currency,
)

AMOUNT_BASIS_NOTE = (
    "Recorded costs may be quotes or planning estimates; their GST basis may be "
    "unknown or mixed. No GST conversion was made. Sinter has not qualified eligible "
    "costs or the application amount; this subtotal is not an eligibility or "
    "application-ceiling decision. Record the grant request and applicant cash or "
    "in-kind contributions separately; this subtotal does not establish them."
)


def quoted_budget_total(rows: list[dict]) -> dict:
    """Sum entered costs exactly, without filling unknown costs or tax."""
    # Admission allows 200 rows at 1e9 AUD x 1e5 quantity: the maximum sum
    # needs 17 integer digits plus two cents digits. Keep its 19 digits exact
    # independently of an embedding caller's precision, traps and exponents.
    # Rounding traps fail closed if a future admission bound exceeds this one.
    with localcontext(
        Context(
            prec=19,
            rounding=ROUND_HALF_EVEN,
            Emin=-999999,
            Emax=999999,
            capitals=1,
            clamp=0,
            flags=[],
            traps=[InvalidOperation, DivisionByZero, Overflow, Inexact, Rounded],
        )
    ):
        known = sum(
            (
                Decimal(row["unit_cost"]) * row["quantity"]
                for row in rows
                if row["unit_cost"] is not None
            ),
            Decimal("0.00"),
        )
        rendered = format(known, ".2f")
    unknown = sum(row["unit_cost"] is None for row in rows)
    complete = bool(rows) and not unknown
    return {
        "known_total": rendered,
        "total": rendered if complete else None,
        "complete": complete,
        "unknown_costs": unknown,
        "unquoted_costs": sum(not row["quote_reference"].strip() for row in rows),
        "items": len(rows),
        "amount_basis_note": AMOUNT_BASIS_NOTE,
    }


def quoted_budget_summary(document: dict, actionable_states: Collection[str]) -> dict:
    """Separate active/history cost sums and retain only raw AUD comparisons.

    An AUD crossing is arithmetic on entered costs, including a known subtotal
    with unpriced lines. False cannot establish an application fits a ceiling.
    Application comparison stays unknown, even when every cost amount exists.
    """
    active_names = {
        row["name"]
        for row in document["opportunities"]
        if row["status"] in actionable_states
    }
    active_rows = [
        row
        for row in document["budget"]
        if not row["opportunity"] or row["opportunity"] in active_names
    ]
    historical_rows = [
        row
        for row in document["budget"]
        if row["opportunity"] and row["opportunity"] not in active_names
    ]
    result = quoted_budget_total(active_rows)
    result["historical"] = quoted_budget_total(historical_rows)
    result["active_items"] = len(active_rows)
    result["historical_items"] = len(historical_rows)
    groups = []
    for opportunity in document["opportunities"]:
        rows = [
            row
            for row in document["budget"]
            if row["opportunity"] == opportunity["name"]
        ]
        totals = quoted_budget_total(rows)
        ceiling = opportunity["ceiling"]
        crossing = (
            Decimal(totals["known_total"]) > Decimal(ceiling)
            if can_compare_ceiling(opportunity)
            else None
        )
        groups.append(
            {
                "opportunity": opportunity["name"],
                **totals,
                "status": opportunity["status"],
                "historical": opportunity["status"] not in actionable_states,
                "ceiling": ceiling,
                "over_ceiling": None,
                "quoted_subtotal_over_ceiling": crossing,
                "ceiling_currency": ceiling_currency(opportunity),
                "comparison_note": ceiling_comparison_note(opportunity),
            }
        )
    result["by_opportunity"] = groups
    result["unallocated_items"] = sum(
        not row["opportunity"] for row in document["budget"]
    )
    return result
