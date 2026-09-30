"""Real-size portfolios fit without weakening campaign admission or recovery."""

import json
import shutil
import subprocess
from pathlib import Path

import pytest

from sinter import campaigns
from sinter.campaign_capacity import text_characters


def portfolio():
    return {
        "title": "Fictional portfolio",
        "assets": [{"name": f"Fictional product {index}",
                    "public_summary": "x" * 3000}
                   for index in range(48)],
    }


def test_large_product_register_is_counted_once_and_survives_reopen(tmp_path):
    store = campaigns.CampaignStore(tmp_path)
    saved = store.save(portfolio())
    assert 144_000 < text_characters(saved["document"]) < 160_000
    reopened = campaigns.CampaignStore(tmp_path).get(saved["id"])
    assert reopened == saved
    assert all(row["public_summary"] == "x" * 3000
               for row in reopened["document"]["assets"])


def test_saved_snapshot_copies_each_consume_space_without_deduplication():
    assert text_characters({"notes": "same", "references": [
        {"notes": "same"}, {"notes": "same"}], "active": True}) == 12
    assert text_characters({"signatory": "A🌱", "sender_role": "B",
                            "contact_details": "CD"}) == 5


def test_exact_unicode_limit_includes_campaign_identity_and_one_more_is_rejected():
    document = campaigns.validate({"title": "Fictional Unicode boundary", "actions": [
        {"task": "🌱" * 4000} for _ in range(49)], "signatory": "Example signer",
        "sender_role": "Example role", "contact_details": "Example contact"})
    room = campaigns.MAX_TEXT_CHARACTERS - text_characters(document)
    document["objective"] = "🌱" * room
    assert text_characters(campaigns.validate(document)) == 200_000
    with pytest.raises(ValueError, match="200,000 text characters"):
        campaigns.validate({**document, "objective": document["objective"] + "🌱"})


def test_normalized_snapshot_admission_keeps_the_encoded_byte_limit(monkeypatch):
    document = campaigns.validate({"title": "Fictional byte boundary", "objective": "🌱" * 100})
    exact = len(json.dumps(document, ensure_ascii=False, allow_nan=False).encode("utf-8"))
    monkeypatch.setattr(campaigns, "MAX_DOCUMENT_BYTES", exact)
    assert campaigns.validate(document) == document
    with pytest.raises(ValueError, match="exceeds 1 MB"):
        campaigns.validate({**document, "objective": document["objective"] + "🌱"})


def test_oversized_update_preserves_saved_portfolio_and_can_retry(tmp_path):
    store = campaigns.CampaignStore(tmp_path)
    saved = store.save(portfolio())
    edited = {**saved["document"], "communications": [
        {"content": "x" * 20000} for _ in range(4)]}
    with pytest.raises(ValueError, match="200,000 text characters"):
        store.save(edited, saved["id"], saved["revision"])
    assert store.get(saved["id"]) == saved
    # The caller retains the oversized editor/backup; only an explicit reduction
    # and retry writes a new revision.
    assert len(edited["communications"]) == 4
    edited["communications"] = edited["communications"][:1]
    retried = store.save(edited, saved["id"], saved["revision"])
    assert retried["revision"] == saved["revision"] + 1
    assert len(retried["document"]["assets"]) == 48


def test_browser_capacity_contract():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required for the campaign capacity display")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run([node, "--test", "tests/campaign_capacity.mjs"],
                            cwd=root, capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
