"""Explicit route-purpose policy; never infer an application or an agreement."""

ROUTE_PURPOSES = frozenset({"unknown", "application", "discussion", "research"})
PURPOSE_LABELS = {
    "unknown": "Not specified",
    "application": "Application",
    "discussion": "Discussion",
    "research": "Research",
}


def non_application_route(row: dict) -> bool:
    """An explicit record purpose does not bypass a required formal workflow."""
    return (row.get("purpose") in {"discussion", "research"}
            and row.get("application_mode") != "required")


def purpose_workflow_conflict(row: dict) -> bool:
    return ((row.get("purpose") in {"discussion", "research"}
             and row.get("application_mode") == "required")
            or (row.get("purpose") == "application"
                and row.get("application_mode") == "not_required"))


def purpose_record_notice(row: dict) -> str:
    """Describe the entered intent without asserting programme requirements."""
    return (PURPOSE_LABELS[row["purpose"]] + " record: retain evidence and next actions. "
            "This purpose does not establish application requirements, eligibility, "
            "authority, acceptance or funding.")
