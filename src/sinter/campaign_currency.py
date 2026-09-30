"""Explicit funding denominations; project costs stay AUD without conversion."""

from __future__ import annotations

from decimal import Decimal

CEILING_CURRENCIES = frozenset(
    {"AUD", "USD", "EUR", "GBP", "NZD", "CAD", "unconfirmed", "other"}
)


def ceiling_currency(row: dict) -> str:
    """Missing legacy denominations retain their previously labelled AUD meaning."""
    value = row.get("ceiling_currency", "AUD")
    if not isinstance(value, str) or value not in CEILING_CURRENCIES:
        raise ValueError(
            "Choose AUD, USD, EUR, GBP, NZD or CAD for the funding ceiling, "
            "or mark its currency unconfirmed or other. Other currencies are "
            "not supported for comparison; retain their exact name in source notes."
        )
    return value


def funding_amount(row: dict) -> str:
    """Present an entered denomination without asserting an award or conversion."""
    if row.get("route_type") == "non_cash_support":
        return "No grant cash (non-cash support)"
    currency = ceiling_currency(row)
    value = row.get("ceiling")
    if value is None:
        if currency == "AUD":
            return "Not recorded"
        label = {"unconfirmed": "unconfirmed", "other": "other (unsupported)"}
        return "Amount not recorded; currency " + label.get(currency, currency)
    amount = Decimal(value)
    rendered = (
        format(amount, ",.0f")
        if amount == amount.to_integral_value()
        else format(amount, ",.2f")
    )
    if currency == "AUD":
        return "A$" + rendered
    if currency in {"unconfirmed", "other"}:
        return rendered + (
            " (currency unconfirmed)"
            if currency == "unconfirmed"
            else " (other currency; comparison unsupported)"
        )
    return currency + " " + rendered


def ceiling_comparison_note(row: dict) -> str:
    """Explain a known ceiling's exclusion from the AUD numeric comparison."""
    if row.get("route_type") == "non_cash_support" or row.get("ceiling") is None:
        return ""
    currency = ceiling_currency(row)
    if currency == "AUD":
        return ""
    if currency == "unconfirmed":
        reason = "Funding ceiling currency is unconfirmed"
    elif currency == "other":
        reason = "Funding ceiling uses another currency (comparison unsupported)"
    else:
        reason = "Funding ceiling is recorded in " + currency
    return reason + (
        "; project costs are AUD. No currency conversion or ceiling comparison "
        "was made. Review the funding terms and costs separately."
    )


def can_compare_ceiling(row: dict) -> bool:
    """Only an entered AUD cash ceiling can be compared with AUD project costs."""
    return (
        row.get("route_type") != "non_cash_support"
        and row.get("ceiling") is not None
        and ceiling_currency(row) == "AUD"
    )
