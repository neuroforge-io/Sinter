"""Copied-workspace qualification must reject lost data and foreign endpoints."""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "upgrade_smoke", Path(__file__).parents[1] / "tools" / "upgrade_smoke.py"
)
upgrade = importlib.util.module_from_spec(spec)
spec.loader.exec_module(upgrade)


def test_additive_defaults_preserve_original_unknowns_and_user_edits():
    original = {
        "id": "retained",
        "document": {
            "status": "unknown",
            "rows": [{"quote": "Original evidence — unchanged", "confirmed": False}],
            "edits": {"markdown": "# User's reviewed draft"},
        },
    }
    current = {
        **original,
        "document": {**original["document"], "new_default": "unknown"},
    }
    upgrade.assert_preserved(original, current, "fixture")
    current["document"]["rows"] = [{"quote": "Replaced evidence", "confirmed": True}]
    with pytest.raises(AssertionError, match="original value"):
        upgrade.assert_preserved(original, current, "fixture")


@pytest.mark.parametrize("changed", [[], [{}, {}], [{"confirmed": 0}]])
def test_recovery_receipt_rejects_removed_added_or_retyped_existing_rows(changed):
    with pytest.raises(AssertionError):
        upgrade.assert_preserved([{"confirmed": False}], changed, "rows")


@pytest.mark.parametrize(
    "address",
    [
        "https://127.0.0.1:1234/",
        "http://example.invalid:1234/",
        "http://localhost:1234/",
        "http://127.0.0.1/",
        "http://user:secret@127.0.0.1:1234/",
        "http://127.0.0.1:1234/api/session",
        "http://127.0.0.1:1234/?token=secret",
        "http://127.0.0.1:1234/#fragment",
    ],
)
def test_upgrade_inspection_rejects_nonlocal_or_credential_addresses(address):
    with pytest.raises(ValueError):
        upgrade.loopback_base(address)
    assert upgrade.loopback_base("http://127.0.0.1:1234/") == "http://127.0.0.1:1234"


def test_fixture_hashing_rejects_links_to_unrelated_workspaces(tmp_path):
    fixture = tmp_path / "fixture"
    fixture.mkdir()
    unrelated = tmp_path / "unrelated.json"
    unrelated.write_text("unrelated confidential workspace")
    (fixture / "link.json").symlink_to(unrelated)
    with pytest.raises(ValueError, match="symbolic links"):
        upgrade.hashes(fixture)
