"""Local answer editing must not release held application content."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sinter import assistant, campaigns, client


def local_document(applicant: str, status: str = "draft") -> dict:
    """Return a small fictional draft with no confirmed applicant."""
    return {
        "title": "Fictional local application practice",
        "organisation": "Example community group",
        "opportunities": [{
            "name": "Fictional equipment route",
            "status": "open",
            "application_mode": "required",
            "applicant": applicant,
            "applicant_confirmed": False,
        }],
        "answers": [{
            "opportunity": "Fictional equipment route",
            "label": "PRIVATE LOCAL QUESTION — explain the proposed activity",
            "text": "  PRIVATE LOCAL DRAFT: café 🐝 é\nCosts remain unknown.\n",
            "limit": 250,
            "status": status,
        }],
    }


@pytest.mark.parametrize("applicant", ["", "Proposed example group"])
@pytest.mark.parametrize("status", ["draft", "reviewed"])
def test_local_drafts_survive_save_reopen_backup_and_restore_but_stay_held(
    tmp_path: Path, applicant: str, status: str,
) -> None:
    store = campaigns.CampaignStore(tmp_path / "original")
    saved = store.save(local_document(applicant, status))
    original = saved["document"]
    original_answer = original["answers"][0]
    reopened = campaigns.CampaignStore(tmp_path / "original").get(saved["id"])
    assert reopened["document"] == original

    backup = json.loads(json.dumps(original, ensure_ascii=False))
    restored = campaigns.CampaignStore(tmp_path / "restored").save(backup)
    assert restored["document"] == original
    assert restored["document"]["opportunities"][0]["applicant_confirmed"] is False

    for document in (original, reopened["document"], restored["document"]):
        report = campaigns.prepare(document)
        assert document["answers"][0] == original_answer
        encoded = json.dumps(report, ensure_ascii=False)
        assert original_answer["text"] not in encoded
        assert original_answer["label"] not in encoded
        assert "PRIVATE LOCAL DRAFT" not in encoded
        assert report["campaign"]["answers"][0]["text"] == ""
        assert report["campaign"]["answers"][0]["limit"] is None
        assert report["answer_metrics"] == []
        assert report["readiness"]["answers_on_unconfirmed_application_routes"] == 1
        assert report["readiness"]["application_workflow_to_confirm"] == 1


def test_explicit_applicant_confirmation_releases_original_local_draft(
    tmp_path: Path,
) -> None:
    store = campaigns.CampaignStore(tmp_path)
    saved = store.save(local_document("Proposed example group"))
    document = saved["document"]
    document["opportunities"][0]["applicant_confirmed"] = True
    confirmed = store.save(document, saved["id"], saved["revision"])
    report = campaigns.prepare(confirmed["document"])
    assert report["campaign"]["answers"][0] == document["answers"][0]
    assert report["readiness"]["application_workflow_to_confirm"] == 0
    assert "signatory authority remain unverified" in report["markdown"]


@pytest.mark.parametrize("applicant", ["", "Proposed example group"])
def test_local_drafts_do_not_expand_assistant_context(
    tmp_path: Path, applicant: str,
) -> None:
    store = campaigns.CampaignStore(tmp_path)
    saved = store.save(local_document(applicant))
    before = store.get(saved["id"])
    payload = {
        "id": saved["id"], "revision": saved["revision"],
        "opportunity": "Fictional equipment route", "task": "enquiry",
    }
    connection = {
        "provider": client.OPENAI_COMPATIBLE,
        "api_url": "https://model.example.invalid/v1", "model": "example-model",
    }
    with patch.object(client, "chat") as model, \
            patch.object(client, "list_models") as discovery, \
            patch.object(client, "connection_identity", return_value=connection), \
            patch.object(client, "validate_chat_request"):
        preview = assistant.preview(store, payload)
        assert preview["context"]["route"]["applicant"] == applicant
        assert preview["context"]["route"]["applicant_confirmed"] is False
        assert "answers" not in preview["context"]
        assert "PRIVATE LOCAL QUESTION" not in preview["content"]
        assert "PRIVATE LOCAL DRAFT" not in preview["content"]
        with pytest.raises(ValueError, match="Confirm the displayed"):
            assistant.run(store, payload)
        model.assert_not_called()
        discovery.assert_not_called()
    assert store.get(saved["id"]) == before
