"""Retain held actions without reporting completion or recommending old work."""

from __future__ import annotations

import copy
import csv
import io
import shutil
import subprocess
from pathlib import Path
from unittest.mock import patch

import pytest

from sinter import campaigns, community


def fixture():
    return {
        "title": "Fictional retained action",
        "organisation": "Example association",
        "objective": "Record current and earlier work without approval.",
        "opportunities": [{"name": "Fictional route", "status": "open"}],
        "actions": [
            {
                "task": "Earlier study 🐝 <exact>",
                "opportunity": "Fictional route",
                "scope_confirmed": True,
                "submission_phase": "pre_submission",
                "owner": "Example coordinator",
                "owner_kind": "role",
                "owner_confirmed": False,
                "due": "2026-09-01",
                "status": "held",
            }
        ],
    }


def test_held_roundtrip_keeps_all_fields_and_does_not_become_current(tmp_path):
    original = campaigns.validate(fixture())
    before = copy.deepcopy(original)
    store = campaigns.CampaignStore(tmp_path)
    saved = store.save(original)
    assert store.get(saved["id"])["document"] == before
    with patch("sinter.client.chat") as model, patch("sinter.client.search") as search:
        report = campaigns.prepare(original)
    model.assert_not_called()
    search.assert_not_called()
    assert original == before
    assert report["campaign"] == before
    assert report["readiness"]["actions_held"] == 1
    assert report["readiness"]["open_actions"] == 0
    assert report["readiness"]["actions_without_owner"] == 0
    assert "On hold · retained, not completed" in report["markdown"]
    assert ("1 action on hold by your choice; retained, not completed, "
            "and excluded from current work") in report["document_markdown"]
    next_action = report["document_markdown"].split("## Next recorded open action", 1)[
        1
    ]
    assert "Earlier study" not in next_action


@pytest.mark.parametrize("status", ["open", "closed", "submitted", "paused"])
def test_route_changes_never_resume_held_action(status):
    document = fixture()
    document["opportunities"][0]["status"] = status
    report = campaigns.prepare(document)
    assert report["campaign"]["actions"][0]["status"] == "held"
    assert report["readiness"]["actions_to_classify"] == 0
    assert report["readiness"]["open_actions"] == 0
    document["actions"][0]["status"] = "open"
    assert campaigns.prepare(document)["readiness"]["open_actions"] == (
        1 if status == "open" else 0
    )


def test_held_shared_export_preserves_csv_without_calendar_deadline():
    rows = [
        {
            "action": "Earlier study 🐝 <exact>",
            "scope": "Fictional route",
            "owner": "Example role (unconfirmed)",
            "due": "2026-09-01",
            "status": "held",
        },
        {"action": "Current work", "due": "2026-10-10", "status": "not_started"},
    ]
    before = copy.deepcopy(rows)
    result = community.plan("Fictional action register", rows)
    assert rows == before
    assert result["actions"][0]["status"] == "held"
    exported = list(csv.DictReader(io.StringIO(result["csv"])))
    assert exported[0]["Action"] == rows[0]["action"]
    assert exported[0]["Status"] == "held"
    assert exported[0]["Proposed target date (unconfirmed)"] == rows[0]["due"]
    assert rows[0]["action"] not in result["calendar"]
    assert "SUMMARY:Current work" in result["calendar"]


def test_old_status_defaults_and_invalid_states_stay_strict():
    document = fixture()
    document["actions"][0].pop("status")
    assert campaigns.validate(document)["actions"][0]["status"] == "open"
    for status in ("done", "open"):
        document["actions"][0]["status"] = status
        assert campaigns.validate(document)["actions"][0]["status"] == status
    document["actions"][0]["status"] = "paused"
    with pytest.raises(ValueError, match="action status"):
        campaigns.validate(document)


def test_campaign_hold_browser_policy():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for campaign hold policy")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--test", "tests/campaign_hold.mjs"],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
