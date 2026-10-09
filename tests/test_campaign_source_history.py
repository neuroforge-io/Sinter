"""Literal source replacement history survives local storage and stays historical."""

import copy
import json
import shutil
import subprocess
from pathlib import Path

import pytest

from sinter import campaigns, client
from sinter.campaign_capacity import text_characters
from sinter.evidence import literal


@pytest.fixture(autouse=True)
def no_remote_work(monkeypatch):
    monkeypatch.setattr(client, "_open", lambda *a, **k: pytest.fail("No remote calls"))
    monkeypatch.setattr(client, "_load_key", lambda: pytest.fail("No credentials"))


def example():
    old_requirement = {
        "opportunity": "Old route name",
        "rule": "Old eligible applicant wording.",
        "status": "met",
        "evidence": "Old applicant note.\r\nNo present confirmation.",
        "source_id": "1" * 32,
        "source_url": "https://example.invalid/original",
        "source_quote": "Original café 中文 e\u0301 🐝\r\n<literal>",
        "checked_at": "2026-09-12",
    }
    old_reference = {
        "kind": "prior_art",
        "source_id": "1" * 32,
        "title": "Original source title",
        "url": "https://example.invalid/original",
        "excerpt": "Original prior-art lead. e\u0301 🐝",
        "checked_at": "2026-09-12",
        "notes": "A lead only; not a novelty conclusion.",
    }
    return {
        "title": "Fictional source replacement",
        "organisation": "Example group",
        "opportunities": [{"name": "Current route", "status": "researching"}],
        "sources": [
            {
                "id": "1" * 32,
                "title": "Refreshed source registry title",
                "url": "https://example.invalid/refreshed",
                "checked_at": "2026-10-09",
            },
            {
                "id": "2" * 32,
                "title": "New source",
                "url": "https://example.invalid/new",
            },
        ],
        "requirements": [
            {
                "opportunity": "Current route",
                "rule": "Current eligible applicant wording.",
                "status": "unknown",
                "evidence": old_requirement["evidence"],
                "source_id": "2" * 32,
                "source_url": "https://example.invalid/new",
                "source_quote": "",
                "checked_at": "",
                "source_history": [
                    {
                        "state": "historical",
                        "reason": "replaced",
                        "record": old_requirement,
                    }
                ],
            }
        ],
        "assets": [
            {
                "name": "Fictional product",
                "stage": "released",
                "prior_art_status": "not_started",
                "references": [
                    {
                        "kind": "prior_art",
                        "source_id": "2" * 32,
                        "title": "New source",
                        "url": "https://example.invalid/new",
                        "excerpt": "",
                        "checked_at": "",
                        "notes": "",
                        "source_history": [
                            {
                                "state": "historical",
                                "reason": "replaced",
                                "record": old_reference,
                                "assessment": {
                                    "status_field": "prior_art_status",
                                    "status": "preliminary_screen",
                                    "date_field": "prior_art_checked_at",
                                    "date": "2026-09-12",
                                },
                            }
                        ],
                    }
                ],
            }
        ],
    }


def test_history_survives_normalization_save_reopen_backup_restore_and_full_notes(
    tmp_path,
):
    document = example()
    before = copy.deepcopy(document)
    normalized = campaigns.validate(document)
    assert document == before
    assert (
        normalized["requirements"][0]["source_history"]
        == before["requirements"][0]["source_history"]
    )
    assert (
        normalized["assets"][0]["references"][0]["source_history"]
        == before["assets"][0]["references"][0]["source_history"]
    )
    store = campaigns.CampaignStore(tmp_path / "first")
    saved = store.save(normalized)
    reopened = campaigns.CampaignStore(tmp_path / "first").get(saved["id"])
    assert reopened["document"] == normalized
    backup = json.loads(json.dumps(reopened["document"], ensure_ascii=False))
    restored = campaigns.CampaignStore(tmp_path / "restored").save(backup)
    assert restored["document"] == normalized
    report = campaigns.prepare(restored["document"])
    assert (
        "Historical source snapshot 1 — unverified; excluded from current checks."
        in report["markdown"]
    )
    for row in [
        normalized["requirements"][0],
        normalized["assets"][0]["references"][0],
    ]:
        entry = row["source_history"][0]
        for value in entry["record"].values():
            if value:
                assert literal(value) in report["markdown"]
    assert "Previous source wording (historical, unverified):" in report["markdown"]
    assert (
        "Previous prior-art assessment (historical, unverified):" in report["markdown"]
    )
    assert "Original café" not in report["document_markdown"]


def test_history_does_not_change_current_readiness_or_product_evidence_gates():
    document = example()
    without_history = copy.deepcopy(document)
    del without_history["requirements"][0]["source_history"]
    del without_history["assets"][0]["references"][0]["source_history"]
    report = campaigns.prepare(document)
    assert report["readiness"] == campaigns.prepare(without_history)["readiness"]
    assert report["readiness"]["requirements_unresolved"] == 1
    assert report["campaign"]["assets"][0]["prior_art_status"] == "not_started"
    document["assets"][0]["prior_art_status"] = "preliminary_screen"
    with pytest.raises(ValueError, match="checked source, date and relevant passage"):
        campaigns.validate(document)


def test_historical_source_rows_cannot_be_removed_while_the_snapshot_is_retained():
    document = example()
    document["sources"] = document["sources"][1:]
    with pytest.raises(ValueError, match="historical requirement points to a source"):
        campaigns.validate(document)
    document["requirements"][0].pop("source_history")
    with pytest.raises(
        ValueError, match="historical asset reference points to a source"
    ):
        campaigns.validate(document)


@pytest.mark.parametrize(
    "change",
    [
        lambda entry: entry.update(state="current"),
        lambda entry: entry.update(reason="verified"),
        lambda entry: entry.update(extra="Unsupported"),
        lambda entry: entry["record"].update(source_history=[]),
        lambda entry: entry["record"].update(status="verified"),
        lambda entry: entry["record"].update(checked_at="2026-02-30"),
        lambda entry: entry["record"].update(source_url="file:///private/source"),
        lambda entry: entry["record"].update(source_quote="x" * 4001),
        lambda entry: entry["record"].update(source_quote="invalid\x00"),
    ],
)
def test_invalid_or_recursive_historical_requirements_fail_closed_without_mutation(
    change,
):
    document = example()
    change(document["requirements"][0]["source_history"][0])
    before = copy.deepcopy(document)
    with pytest.raises(ValueError):
        campaigns.validate(document)
    assert document == before


def test_historical_assessment_must_match_the_original_reference_workstream():
    document = example()
    document["assets"][0]["references"][0]["source_history"][0]["assessment"][
        "status_field"
    ] = "rights_status"
    with pytest.raises(ValueError, match="match its previous evidence type"):
        campaigns.validate(document)


def test_history_uses_existing_requirement_and_reference_caps_without_pruning():
    document = example()
    document["requirements"].extend(
        {"opportunity": "Current route", "rule": f"Check {index}"}
        for index in range(199)
    )
    before = copy.deepcopy(document)
    with pytest.raises(ValueError, match="including historical source snapshots"):
        campaigns.validate(document)
    assert document == before
    document = example()
    references = document["assets"][0]["references"]
    references.extend(
        {"kind": "other", "title": f"Reference {index}"} for index in range(19)
    )
    before = copy.deepcopy(document)
    with pytest.raises(ValueError, match="including historical source snapshots"):
        campaigns.validate(document)
    assert document == before


def test_blank_reference_cannot_hide_malformed_history():
    document = example()
    document["assets"][0]["references"] = [{"kind": "other", "source_history": {}}]
    with pytest.raises(ValueError, match="historical snapshots"):
        campaigns.validate(document)


def test_oversized_history_update_leaves_saved_work_and_original_snapshots_intact(
    tmp_path,
):
    proposed = example()
    document = copy.deepcopy(proposed)
    del document["requirements"][0]["source_history"]
    del document["assets"][0]["references"][0]["source_history"]
    document["actions"] = [{"task": "🌱" * 4000} for _ in range(49)]
    normalized = campaigns.validate(document)
    normalized["objective"] = "🌱" * (200_000 - text_characters(normalized))
    assert text_characters(campaigns.validate(normalized)) == 200_000
    assert campaigns.MAX_TEXT_CHARACTERS == 200_000
    assert campaigns.MAX_DOCUMENT_BYTES == 1_000_000
    store = campaigns.CampaignStore(tmp_path)
    saved = store.save(normalized)
    candidate = copy.deepcopy(normalized)
    candidate["requirements"][0]["source_history"] = proposed["requirements"][0][
        "source_history"
    ]
    candidate["assets"][0]["references"][0]["source_history"] = proposed["assets"][0][
        "references"
    ][0]["source_history"]
    before = copy.deepcopy(candidate)
    with pytest.raises(ValueError, match="200,000 text characters"):
        store.save(candidate, saved["id"], saved["revision"])
    assert store.get(saved["id"]) == saved
    assert candidate == before


def test_source_replacement_pure_javascript_regressions():
    node = shutil.which("node")
    if not node:
        pytest.skip("Node is required for pure JavaScript regressions")
    result = subprocess.run(
        [node, "--test", str(Path(__file__).with_name("campaign_source_history.mjs"))],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    assert result.returncode == 0, result.stdout + result.stderr
