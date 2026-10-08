"""Fictional focused copies retain evidence without editing their parents."""

import copy
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from sinter import campaigns, client
from sinter.campaign_capacity import text_characters
from sinter.runtime import Runtime, catalog


@pytest.fixture(autouse=True)
def fictional_environment(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    monkeypatch.setenv("SINTER_DATA_DIR", str(tmp_path / "workspace"))
    monkeypatch.setattr(client, "_open", lambda *a, **k: pytest.fail("No remote call"))
    monkeypatch.setattr(client, "_load_key", lambda: pytest.fail("No credential read"))


def portfolio():
    route = "Fictional paused equipment route"
    other = "Fictional other route"
    return {
        "title": "Fictional portfolio 🌱",
        "organisation": "Example community group",
        "objective": "Keep unanswered questions open.\nNo authority recorded.",
        "opportunities": [
            {
                "name": route,
                "status": "paused",
                "window_source_id": "1" * 32,
                "window_source_quote": "Old window wording.",
                "window_source_url": "https://example.invalid/old-window",
                "window_checked_at": "2026-09-12",
            },
            {"name": other, "status": "researching"},
        ],
        "sources": [
            {},
            {
                "id": "1" * 32,
                "title": "Refreshed guidelines",
                "url": "https://example.invalid/new-guidelines",
                "checked_at": "2026-10-08",
                "notes": "New wording, not the old quote.",
            },
            {
                "id": "2" * 32,
                "title": "Historical correspondence reference",
                "url": "https://example.invalid/opaque-message",
                "checked_at": "",
            },
            {
                "id": "3" * 32,
                "title": "Product rights reference",
                "url": "https://example.invalid/rights",
                "checked_at": "2026-09-15",
            },
            {"id": "4" * 32, "title": "Separate research lead", "notes": "Unlinked."},
        ],
        "requirements": [
            {
                "opportunity": route,
                "rule": "Confirm eligible applicant.",
                "status": "clarification",
                "evidence": "No confirmation recorded.",
                "source_id": "1" * 32,
                "source_url": "https://example.invalid/old",
                "source_quote": "Original café 中文 e\u0301 wording.",
                "checked_at": "2026-09-12",
            },
            {"opportunity": other, "rule": "Other criterion.", "status": "unknown"},
        ],
        "answers": [
            {
                "opportunity": route,
                "label": "Historical full answer",
                "text": "Keep this held answer exactly.\r\n🌱 <not HTML>",
                "limit": 20,
                "status": "draft",
            },
            {"opportunity": other, "label": "Other answer", "text": "Other work."},
        ],
        "budget": [
            {
                "opportunity": route,
                "item": "Quoted item",
                "quantity": 2,
                "unit_cost": None,
                "quote_reference": "No quote received.",
            },
            {"opportunity": "", "item": "Campaign-wide item", "unit_cost": "12.00"},
        ],
        "actions": [
            {
                "opportunity": route,
                "task": "Confirm costs",
                "owner": "Undetermined",
                "owner_kind": "unknown",
                "owner_confirmed": False,
                "scope_confirmed": False,
                "due": "",
                "status": "held",
            },
            {
                "opportunity": "",
                "task": "Unassigned shared action",
                "owner": "",
                "owner_kind": "unassigned",
                "due": "",
                "status": "open",
            },
        ],
        "communications": [
            {
                "opportunity": route,
                "direction": "incoming",
                "status": "received",
                "date": "2026-09-14",
                "content": "Old received clarification.",
                "evidence_links": [
                    {
                        "source_id": "2" * 32,
                        "title": "Original message snapshot",
                        "url": "https://example.invalid/old-message",
                        "notes": "Original recorded context",
                        "checked_at": "2026-09-14",
                    }
                ],
            },
            {
                "opportunity": route,
                "direction": "outgoing",
                "status": "sent",
                "date": "2026-09-13",
                "content": "Original sent enquiry.",
            },
            {
                "opportunity": route,
                "direction": "outgoing",
                "status": "draft",
                "date": "",
                "content": "Unsent follow-up.",
            },
            {
                "opportunity": "",
                "direction": "outgoing",
                "status": "draft",
                "content": "Campaign-wide draft.",
            },
        ],
        "assets": [
            {
                "id": "a" * 32,
                "name": "Fictional linked product",
                "funding_opportunities": [route, other],
                "rights_status": "public_license_stated",
                "references": [
                    {
                        "kind": "rights",
                        "source_id": "3" * 32,
                        "title": "Original rights snapshot",
                        "url": "https://example.invalid/old-rights",
                        "excerpt": "Original licence wording.",
                        "checked_at": "2026-09-15",
                    }
                ],
            }
        ],
    }


def focus(document, **kwargs):
    return campaigns.focused_document(
        document,
        document["opportunities"][0]["name"],
        "Fictional focused case",
        **kwargs,
    )


def test_exact_selected_history_unknowns_and_original_row_lineage_survive():
    original = portfolio()
    before = copy.deepcopy(original)
    normalized = campaigns.validate(original)
    result = focus(original, parent={"id": "f" * 32, "revision": 49, "dirty": True})
    document = result["document"]
    for key in ("requirements", "answers", "budget", "actions", "opportunities"):
        assert document[key] == normalized[key][:1]
    assert document["communications"] == normalized["communications"][:3]
    assert [row["status"] for row in document["communications"]] == [
        "received",
        "sent",
        "draft",
    ]
    assert document["assets"] == []
    assert document["sources"][:-1] == normalized["sources"][:2]
    assert document["requirements"][0]["source_url"] != document["sources"][0]["url"]
    assert document["requirements"][0]["checked_at"] == "2026-09-12"
    assert result["included"]["sources"] == [2, 3]
    assert result["omitted"]["sources"] == [4, 5]
    assert result["included_material"]["answers"] == normalized["answers"][:1]
    assert result["omitted_material"]["answers"] == normalized["answers"][1:]
    expected_hash = hashlib.sha256(
        json.dumps(
            original,
            ensure_ascii=False,
            sort_keys=True,
            allow_nan=False,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()
    assert result["parent"]["snapshot_sha256"] == expected_hash
    lineage = document["sources"][-1]
    assert lineage["checked_at"] == lineage["url"] == ""
    assert '"revision":49' in lineage["notes"]
    assert "not source verification" in lineage["notes"]
    assert original == before
    document["answers"][0]["text"] = "Changed in the separate copy."
    assert original == before


def test_explicit_shared_material_and_cross_route_dependencies_keep_links():
    original = portfolio()
    normalized = campaigns.validate(original)
    result = focus(
        original,
        options={"campaign_wide": True, "linked_assets": True, "all_sources": True},
    )
    document = result["document"]
    assert document["assets"] == normalized["assets"]
    assert document["opportunities"] == normalized["opportunities"]
    assert result["dependency_routes"] == [original["opportunities"][1]["name"]]
    assert document["budget"] == normalized["budget"]
    assert document["actions"] == normalized["actions"]
    assert document["communications"] == normalized["communications"]
    assert document["sources"][:-1] == normalized["sources"]
    # Dependency routes are retained as recorded, not silently expanded to their work.
    assert document["answers"] == normalized["answers"][:1]
    assert document["requirements"] == normalized["requirements"][:1]


def test_later_selected_route_keeps_original_order_and_earlier_dependency():
    original = portfolio()
    selected = original["opportunities"][0]["name"]
    original["opportunities"].reverse()
    before = copy.deepcopy(original)
    result = campaigns.focused_document(
        original, selected, "Fictional later route", {"linked_assets": True}
    )
    assert [row["name"] for row in result["document"]["opportunities"]] == [
        row["name"] for row in original["opportunities"]
    ]
    assert result["route"] == selected
    assert result["document"]["opportunities"][1]["name"] == selected
    assert result["dependency_routes"] == [original["opportunities"][0]["name"]]
    assert result["document"]["answers"][0]["text"] == original["answers"][0]["text"]
    assert original == before


def test_shared_local_operation_never_saves_until_explicit_new_id(tmp_path):
    with (
        patch("socket.socket", side_effect=AssertionError("No socket")),
        Runtime(tmp_path) as app,
    ):
        original = app.call("campaigns.save", {"document": portfolio()})
        result = app.call(
            "campaigns.focus",
            {
                "document": original["document"],
                "opportunity": original["document"]["opportunities"][0]["name"],
                "title": "Fictional focused case",
                "parent": {"id": original["id"], "revision": original["revision"]},
            },
        )
        assert len(app.call("campaigns.list")["campaigns"]) == 1
        assert app.call("campaigns.get", {"id": original["id"]}) == original
        copied = app.call("campaigns.save", {"document": result["document"]})
        assert copied["id"] != original["id"] and copied["revision"] == 1
        assert app.call("campaigns.get", {"id": original["id"]}) == original
        assert len(app.call("campaigns.list")["campaigns"]) == 2
    operation = next(
        row for row in catalog()["operations"] if row["id"] == "campaigns.focus"
    )
    assert operation["effect"] == "local"


def test_full_unicode_selection_refuses_provenance_overflow_without_truncation():
    original = campaigns.validate(
        {
            "title": "Fictional boundary",
            "opportunities": [{"name": "Fictional chosen route"}],
            "answers": [
                {
                    "opportunity": "Fictional chosen route",
                    "label": f"Answer {i}",
                    "text": "🌱" * 20000,
                }
                for i in range(9)
            ],
        }
    )
    original["actions"] = [
        {"opportunity": "Fictional chosen route", "task": "🌱" * 4000} for _ in range(4)
    ]
    original = campaigns.validate(original)
    original["objective"] = "🌱" * (200000 - text_characters(original))
    original = campaigns.validate(original)
    before = copy.deepcopy(original)
    with pytest.raises(ValueError, match="200,000 text characters"):
        focus(original)
    assert original == before


def test_encoded_byte_and_source_row_limits_remain_authoritative(monkeypatch):
    original = campaigns.validate(portfolio())
    projected = focus(original)["document"]
    encoded = len(json.dumps(projected, ensure_ascii=False, allow_nan=False).encode())
    monkeypatch.setattr(campaigns, "MAX_DOCUMENT_BYTES", encoded - 1)
    with pytest.raises(ValueError, match="1 MB"):
        focus(original)
    monkeypatch.setattr(campaigns, "MAX_DOCUMENT_BYTES", 1000000)
    original["sources"] = [
        {"id": f"{index:032x}", "title": f"Source {index}"} for index in range(100)
    ]
    # Remove now-unavailable links without inventing replacement evidence.
    original["opportunities"][0]["window_source_id"] = ""
    original["requirements"][0]["source_id"] = ""
    original["communications"][0]["evidence_links"][0]["source_id"] = ""
    original["assets"][0]["references"][0]["source_id"] = ""
    before = copy.deepcopy(original)
    with pytest.raises(ValueError, match="100"):
        focus(original, options={"all_sources": True})
    assert original == before


@pytest.mark.parametrize(
    "kwargs",
    [
        {"options": {"campaign_wide": "yes"}},
        {"options": False},
        {"options": {"unexpected": True}},
        {"parent": {"revision": 1}},
        {"parent": {"id": "invalid", "revision": 1}},
        {"parent": {"dirty": "yes"}},
    ],
)
def test_invalid_selection_metadata_does_not_change_parent(kwargs):
    original = portfolio()
    before = copy.deepcopy(original)
    with pytest.raises(ValueError):
        focus(original, **kwargs)
    assert original == before


@pytest.mark.parametrize("arguments, code", [(["--help"], 0), ([], 2)])
def test_browser_tool_setup_precedes_optional_dependencies(arguments, code, tmp_path):
    environment = dict(os.environ)
    environment.pop("SINTER_CHROMIUM", None)
    environment["TMPDIR"] = str(tmp_path)
    root = Path(__file__).resolve().parents[1]
    before = set(tmp_path.iterdir())
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            str(root / "tools/campaign_focus_browser.py"),
            *arguments,
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == code, result.stderr
    assert "Traceback" not in result.stderr
    if code == 0:
        assert "usage:" in result.stdout and "--chromium" in result.stdout
    else:
        assert "Playwright is required" in result.stderr
    assert set(tmp_path.iterdir()) == before
