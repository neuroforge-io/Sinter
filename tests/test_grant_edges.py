"""Missing values must not pass checks; extreme dates must not break calendars."""
from datetime import date

import pytest

from sinter.evidence import source
from sinter.grants import confirmed_deadline, screen


@pytest.mark.parametrize("operator", ["equals", "contains"])
@pytest.mark.parametrize("actual,expected", [(" ", " "), ("P&C", "\t"), ("\n", "P&C")])
def test_whitespace_is_unknown_not_eligible(operator, actual, expected):
    reference = source("Fixture guidance", "Applicants must be P&C associations.", kind="reference_excerpt")
    rule = {"field": "organisation_type", "operator": operator, "value": expected,
            "source_id": reference.id, "quote": reference.content, "confirmed": True}
    result = screen({"organisation_type": actual}, [rule], [reference])
    assert result["status"] == "review_required"
    assert result["checks"][0]["status"] == "unknown"


def test_unrepresentable_deadline_is_rejected():
    with pytest.raises(ValueError, match="calendar end date"):
        confirmed_deadline(date.max.isoformat())
    assert confirmed_deadline("2026-12-31") == "2026-12-31"
