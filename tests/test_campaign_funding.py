"""Fictional funding totals; real private applications never belong in fixtures."""
from __future__ import annotations

import copy
import hashlib
import io
import json
from datetime import date, timedelta
from decimal import InvalidOperation, localcontext
from unittest.mock import patch

import pytest

from sinter import assistant, campaigns, cli, client
from sinter.runtime import Runtime, catalog
from test_runtime import post, server as runtime_server

server = runtime_server


@pytest.fixture(autouse=True)
def no_remote_or_credentials(tmp_path, monkeypatch):
    monkeypatch.setenv("SINTER_DATA_DIR", str(tmp_path / "workspace"))
    for key in ("NEUROFORGE_API_KEY", "SINTER_API_KEY", "NEUROFORGE_BASE_URL", "NEUROFORGE_MODEL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setattr(client, "_open", lambda *a, **k: pytest.fail("No remote requests"))
    monkeypatch.setattr(client, "_load_key", lambda: pytest.fail("No credentials"))


def amount(value=None, currency="AUD"):
    return {"amount": value, "currency": currency, "notes": "Wholly fictional entered evidence"}


def route(name="Fictional Maple round", *, status="open", kind="cash", application="preparing"):
    today = date.today().isoformat()
    source_id = hashlib.sha256(name.encode()).hexdigest()[:32]
    claim = {"source_id": source_id, "source_url": "https://example.invalid/fictional-terms/" + source_id,
             "source_quote": "Fictional community applicants may request up to 8,000 units.",
             "checked_at": today, "evidence": "Fictional applicant assessment only"}
    return {"name": name, "route_type": "cash_grant" if kind == "cash" else "non_cash_support",
            "status": status, "ceiling": "8000", "ceiling_currency": "AUD",
            "url": claim["source_url"], "application_window": "rolling",
            "window_source_id": source_id, "window_source_url": claim["source_url"],
            "window_source_quote": "Fictional applications accepted year-round.",
            "window_checked_at": today,
            "funding_tracking": {"round_key": name, "benefit_type": kind,
                "eligibility": "eligible", "ceiling_scope": "individual",
                "eligibility_evidence": copy.deepcopy(claim), "ceiling_evidence": copy.deepcopy(claim),
                "application_status": application, "target": amount("3000"),
                "requested": amount(), "awarded": amount(), "received": amount()}}


def campaign(*rows):
    selected = list(rows or [route()])
    return {"title": "Fictional funding tracker", "opportunities": selected,
            "sources": [{"id": row["window_source_id"], "title": "Fictional terms — " + row["name"],
                         "url": row["window_source_url"], "checked_at": row["window_checked_at"]}
                        for row in selected if row.get("window_source_id")]}


def group(result, stage, kind="cash", currency="AUD"):
    return next(row for row in result["stages"][stage]["groups"]
                if (row["benefit_type"], row["currency"]) == (kind, currency))


def test_ceilings_targets_requests_and_recorded_receipts_are_distinct():
    preparing = route()
    submitted = route("Fictional Oak round", status="submitted", application="submitted")
    submitted["funding_tracking"].update(requested=amount("1250.55"), award_status="awarded",
                                         receipt_status="received", awarded=amount("1100"), received=amount("500"))
    result = campaigns.funding_summary(campaign(preparing, submitted))
    assert result["schema"] == "sinter-funding-summary/v1"
    assert result["scope"] == "current_campaign"
    for stage, expected in (("available", "8000.00"), ("targets", "3000.00"),
                            ("submitted", "1250.55"), ("awarded", "1100.00"), ("received", "500.00")):
        assert group(result, stage)["total"] == expected
    assert "grand_total" not in result
    assert result["counts"]["applications"] == {"preparing": 1, "submitted": 1}
    assert "do not add them together" in result["notice"]


def test_url_less_amounts_survive_restore_without_creating_funding_events(tmp_path):
    row = route()
    document = campaign(row)
    source = {"id": "d" * 32, "title": "Fictional retained planning record",
              "url": "", "checked_at": date.today().isoformat(),
              "notes": "Fictional working record, not official funding terms."}
    document["sources"].append(source)
    for key, value in (("target", "15000.00"), ("requested", "1000.00"),
                       ("awarded", "500.00"), ("received", "50.00")):
        row["funding_tracking"][key] = {
            "amount": value, "currency": "AUD", "source_id": source["id"],
            "source_url": "", "checked_at": source["checked_at"],
            "source_quote": f"Fictional {key} wording, unverified.",
            "notes": f"Original {key} note.",
        }
    before = copy.deepcopy(document)
    summary = campaigns.funding_summary(document)
    assert document == before
    assert group(summary, "targets")["total"] == "15000.00"
    assert group(summary, "available")["total"] == "8000.00"
    for stage in ("submitted", "awarded", "received"):
        assert summary["stages"][stage]["groups"] == []
    assert summary["counts"]["applications"] == {"preparing": 1}
    assert summary["counts"]["awards"] == {"unknown": 1}
    assert summary["counts"]["receipts"] == {"unknown": 1}
    store = campaigns.CampaignStore(tmp_path)
    saved = store.save(document)
    expected = campaigns.validate(document)
    assert saved["document"] == expected
    reopened = campaigns.CampaignStore(tmp_path).get(saved["id"])
    assert reopened == saved
    restored = store.save(json.loads(json.dumps(reopened["document"])))
    assert restored["id"] != saved["id"] and restored["document"] == expected
    assert campaigns.funding_summary(restored["document"]) == summary
    assert store.get(saved["id"]) == saved


@pytest.mark.parametrize("component,reason", [
    ("eligibility_evidence", "eligibility_evidence_missing"),
    ("ceiling_evidence", "ceiling_evidence_missing"),
    ("window", "window_unconfirmed"),
])
def test_url_less_source_cannot_support_available_funding(component, reason):
    row = route()
    document = campaign(row)
    source = {"id": "d" * 32, "title": "Fictional URL-less source record",
              "url": "", "checked_at": date.today().isoformat()}
    document["sources"].append(source)
    if component == "window":
        row.update(window_source_id=source["id"], window_source_url="",
                   window_checked_at=source["checked_at"])
    else:
        row["funding_tracking"][component].update(
            source_id=source["id"], source_url="", checked_at=source["checked_at"])
    before = copy.deepcopy(document)
    summary = campaigns.funding_summary(document)
    assert summary["stages"]["available"]["groups"] == []
    assert any(item["reason"] == reason for item in summary["exclusions"])
    assert group(summary, "targets")["total"] == "3000.00"
    assert document == before


def test_currencies_cash_and_credits_never_mix_and_unknown_is_not_zero():
    rows = [route("Fictional Birch", status="submitted", application="submitted"),
            route("Fictional Pine", status="submitted", application="submitted"),
            route("Fictional Cloud credits", status="submitted", kind="credits", application="submitted"),
            route("Fictional Unknown", status="submitted", application="submitted")]
    for row, value, currency in zip(rows, ("1.01", "42000", "7500", None), ("AUD", "USD", "USD", "USD")):
        row["funding_tracking"]["requested"] = amount(value, currency)
    result = campaigns.funding_summary(campaign(*rows))
    assert group(result, "submitted")["total"] == "1.01"
    assert group(result, "submitted", currency="USD")["known_total"] == "42000.00"
    assert group(result, "submitted", currency="USD")["total"] is None
    assert group(result, "submitted", currency="USD")["unknown_amounts"] == 1
    assert group(result, "submitted", "credits", "USD")["total"] == "7500.00"
    unknown = campaigns.funding_summary(campaign(rows[-1]))
    assert group(unknown, "submitted", currency="USD")["known_total"] is None
    rows[-1]["funding_tracking"]["requested"] = amount("0", "USD")
    zero = campaigns.funding_summary(campaign(rows[-1]))
    assert group(zero, "submitted", currency="USD")["total"] == "0.00"


def test_submission_history_distinguishes_cash_credits_eois_and_closed_events(tmp_path):
    cash = [route(f"Fictional cash round {index}", status="submitted", application="submitted")
            for index in range(6)]
    for row in cash[:-1]:
        row["funding_tracking"]["requested"] = amount("10")
    credit = route("Fictional current credits", status="submitted", kind="credits", application="submitted")
    historical = route("Fictional historic credits", status="closed", kind="credits", application="submitted")
    historical["funding_tracking"]["closure_reason"] = "round_closed"
    investors = [route(f"Fictional investment EOI {index}", status="submitted", application="submitted")
                 for index in range(3)]
    for row in investors:
        row["route_type"] = "equity"
        row["funding_tracking"]["requested"] = amount("999")
    document = campaign(*cash, credit, historical, *investors)
    result = campaigns.funding_summary(document)
    history = result["counts"]["submission_history"]
    assert result["stages"]["submitted"]["opportunities"] == 11
    assert history["ever_recorded"] == {"cash": 6, "credits": 2, "equity": 3}
    assert history["not_marked_closed"] == {"cash": 6, "credits": 1, "equity": 3}
    assert history["marked_closed"] == {"credits": 1}
    assert history["closure_conflicting"] == {} and history["application_conflicting"] == 0
    assert "Cash: 6" in result["markdown"] and "Investment / EOI: 3" in result["markdown"]
    assert "Submitted requests — all recorded history (11 rounds / records)" in result["markdown"]
    assert "verified current application window" in history["notice"]
    assert "Eligible recorded ceilings — not guaranteed" in result["markdown"]
    assert group(result, "submitted")["known_total"] == "50.00"
    assert group(result, "submitted")["total"] is None
    with Runtime(tmp_path / "fictional-mixed-submissions") as runtime:
        assert runtime.call("campaigns.funding_summary", {"document": document}) == result


def test_duplicate_types_and_closure_states_are_not_double_counted():
    current = route("Fictional current duplicate", status="submitted", application="submitted")
    closed = route("Fictional closed duplicate", status="closed", kind="credits", application="submitted")
    for row in (current, closed):
        row["funding_tracking"]["round_key"] = "Fictional same round"
    result = campaigns.funding_summary(campaign(current, closed))
    history = result["counts"]["submission_history"]
    assert history["ever_recorded"] == {"conflicting_type": 1}
    assert history["not_marked_closed"] == history["marked_closed"] == {}
    assert history["closure_conflicting"] == {"conflicting_type": 1}
    assert result["counts"]["duplicate_rounds"] == 1
    assert "Closure state conflicting: Conflicting type: 1" in result["markdown"]


def test_contradictory_duplicate_application_states_do_not_invent_submissions():
    submitted = route("Fictional submitted duplicate", status="submitted", application="submitted")
    preparing = route("Fictional preparing duplicate")
    for row in (submitted, preparing):
        row["funding_tracking"]["round_key"] = "Fictional unresolved round"
    history = campaigns.funding_summary(campaign(submitted, preparing))["counts"]["submission_history"]
    assert history["ever_recorded"] == {} and history["not_marked_closed"] == {}
    assert history["application_conflicting"] == 1


def test_legacy_unclassified_submissions_do_not_become_cash_grants():
    row = route("Fictional legacy submitted", status="submitted", application="submitted")
    del row["funding_tracking"]
    original = copy.deepcopy(row)
    result = campaigns.funding_summary(campaign(row))
    assert result["counts"]["submission_history"]["ever_recorded"] == {"unclassified": 1}
    assert result["counts"]["submission_history"]["not_marked_closed"] == {"unclassified": 1}
    assert row == original


@pytest.mark.parametrize("currency", ["unconfirmed", "other"])
def test_unconfirmed_denominations_never_produce_numeric_totals(currency):
    row = route(status="submitted", application="submitted")
    row["funding_tracking"]["requested"] = amount("400", currency)
    result = campaigns.funding_summary(campaign(row))
    value = group(result, "submitted", currency=currency)
    assert value["known_total"] is None and value["total"] is None
    assert value["excluded_amounts"] == 1
    assert any(item["reason"] == "currency_unconfirmed" for item in result["exclusions"])


@pytest.mark.parametrize("change,reason", [
    ({"eligibility": "unknown"}, "eligibility_unconfirmed"),
    ({"eligibility": "ineligible"}, "ineligible"),
    ({"ceiling_scope": "program_pool"}, "ceiling_not_individual"),
    ({"ceiling_scope": "unknown"}, "ceiling_not_individual"),
    ({"eligibility_evidence": {}}, "eligibility_evidence_missing"),
    ({"ceiling_evidence": {}}, "ceiling_evidence_missing"),
])
def test_available_is_not_inferred_from_open_status_or_large_ceiling(change, reason):
    row = route(); row["funding_tracking"].update(change)
    result = campaigns.funding_summary(campaign(row))
    assert not result["stages"]["available"]["groups"]
    assert any(item["reason"] == reason for item in result["exclusions"])
    assert group(result, "targets")["total"] == "3000.00"


def test_source_update_stale_future_checks_and_expired_window_exclude_available():
    for changed_date in (date.today() - timedelta(days=91), date.today() + timedelta(days=1)):
        row = route()
        row["funding_tracking"]["eligibility_evidence"]["checked_at"] = changed_date.isoformat()
        assert not campaigns.funding_summary(campaign(row))["stages"]["available"]["groups"]
    row = route(); row["deadline"] = (date.today() - timedelta(days=1)).isoformat()
    row["application_window"] = "fixed"
    assert any(item["reason"] == "window_unconfirmed"
               for item in campaigns.funding_summary(campaign(row))["exclusions"])
    row = route(); source_id = "a" * 32
    row["funding_tracking"]["ceiling_evidence"]["source_id"] = source_id
    original = campaign(row)
    original["sources"].append({"id": source_id, "title": "Fictional changed terms",
                               "url": "https://example.invalid/new-terms", "checked_at": date.today().isoformat()})
    assert any(item["reason"] == "ceiling_evidence_missing"
               for item in campaigns.funding_summary(original)["exclusions"])


def test_closed_never_erases_historical_submission_award_or_receipt():
    row = route(status="closed", application="submitted")
    row["funding_tracking"].update(closure_reason="round_closed", requested=amount("100"),
        award_status="awarded", awarded=amount("80"), receipt_status="received", received=amount("40"))
    result = campaigns.funding_summary(campaign(row))
    for stage, expected in (("submitted", "100.00"), ("closed", "100.00"),
                            ("awarded", "80.00"), ("received", "40.00")):
        assert group(result, stage)["total"] == expected
    assert not result["stages"]["available"]["groups"]
    assert result["counts"]["closed_outcomes"] == {"round_closed": 1}
    row["funding_tracking"]["closure_reason"] = "declined"
    declined = campaigns.funding_summary(campaign(row))
    assert declined["counts"]["closed_outcomes"] == {"declined": 1}
    assert "Closed outcomes: declined: 1." in declined["markdown"]
    assert group(declined, "received")["total"] == "40.00"


def test_duplicate_rounds_are_deduplicated_and_all_amounts_excluded():
    first = route("Fictional first record", status="closed", application="submitted")
    second = route("Fictional alias record", status="closed", kind="credits", application="submitted")
    first["funding_tracking"].update(round_key="  Example   ROUND  ", requested=amount("100"), closure_reason="declined")
    second["funding_tracking"].update(round_key="example round", requested=amount("200"), closure_reason="withdrawn")
    result = campaigns.funding_summary(campaign(first, second))
    assert result["counts"]["identified_rounds"] == 1
    assert result["counts"]["duplicate_rounds"] == 1 and result["counts"]["duplicate_rows"] == 1
    assert result["stages"]["submitted"]["opportunities"] == 1
    assert result["counts"]["closed_outcomes"] == {"conflicting": 1}
    assert all(item["total"] is None for item in result["stages"]["submitted"]["groups"])
    assert all(item["reason"] == "duplicate_round" for item in result["exclusions"]
               if item["stage"] in {"submitted", "closed"})


@pytest.mark.parametrize("state,reason", [("unknown", "state_unconfirmed"),
                                         ("not_applied", "inactive_stage")])
def test_entered_inactive_amounts_are_retained_and_visibly_excluded(state, reason):
    row = route(status="closed", application=state)
    row["funding_tracking"].update(requested=amount("100"), awarded=amount("80"),
        received=amount("40"), award_status="unknown", receipt_status="not_received")
    before = copy.deepcopy(row)
    result = campaigns.funding_summary(campaign(row))
    exclusions = {(item["stage"], item["reason"]) for item in result["exclusions"]}
    assert {("submitted", reason), ("closed", reason),
            ("awarded", "state_unconfirmed"), ("received", "inactive_stage")} <= exclusions
    assert all(not result["stages"][stage]["groups"]
               for stage in ("submitted", "closed", "awarded", "received"))
    assert "Entered amount is retained" in result["markdown"] and row == before


def test_explicit_not_awarded_receipt_conflict_preserves_record_without_total():
    row = route(status="closed", application="submitted")
    row["funding_tracking"].update(requested=amount("100"), award_status="not_awarded",
        receipt_status="received", received=amount("40"), closure_reason="round_closed")
    before = copy.deepcopy(row)
    result = campaigns.funding_summary(campaign(row))
    assert result["counts"]["receipts"] == {"conflicting": 1}
    assert group(result, "received")["total"] is None
    assert any(item["reason"] == "receipt_conflict" for item in result["exclusions"])
    assert group(result, "submitted")["total"] == group(result, "closed")["total"] == "100.00"
    assert row == before
    # An unknown award is not an assertion that a recorded receipt is impossible.
    row["funding_tracking"]["award_status"] = "unknown"
    assert group(campaigns.funding_summary(campaign(row)), "received")["total"] == "40.00"


def test_application_route_conflict_keeps_explicit_award_and_receipt_history():
    row = route(status="submitted", application="not_applied")
    row["funding_tracking"].update(requested=amount("100"), award_status="awarded",
        awarded=amount("80"), receipt_status="received", received=amount("40"))
    result = campaigns.funding_summary(campaign(row))
    assert group(result, "submitted")["total"] is None
    assert group(result, "awarded")["total"] == "80.00"
    assert group(result, "received")["total"] == "40.00"
    assert result["counts"]["applications"] == {"conflicting": 1}


def test_legacy_submission_and_contradictory_tracking_do_not_invent_or_erase_amounts():
    row = route(status="submitted", application="not_applied")
    result = campaigns.funding_summary(campaign(row))
    assert result["counts"]["applications"] == {"conflicting": 1}
    assert group(result, "submitted")["total"] is None
    assert any(item["reason"] == "status_conflict" for item in result["exclusions"])
    del row["funding_tracking"]
    result = campaigns.funding_summary(campaign(row))
    assert result["counts"]["applications"] == {"submitted": 1}
    assert result["counts"]["missing_round_keys"] == 1
    assert result["stages"]["submitted"]["groups"][0]["unknown_amounts"] == 1
    assert result["stages"]["submitted"]["groups"][0]["known_total"] is None


@pytest.mark.parametrize("route_type", ["equity", "matched_voucher", "tax_incentive", "non_cash_support"])
def test_other_financing_and_expense_support_are_not_cash(route_type):
    row = route(status="submitted", application="submitted"); row["route_type"] = route_type
    row["funding_tracking"]["requested"] = amount("999")
    result = campaigns.funding_summary(campaign(row))
    assert group(result, "submitted")["total"] is None
    assert any(item["reason"] == "unsupported_benefit" for item in result["exclusions"])


@pytest.mark.parametrize("value", [True, "-1", "NaN", "1e3", "2.001", "1000000001", {}, []])
def test_invalid_amount_cannot_replace_a_saved_campaign(value, tmp_path):
    store = campaigns.CampaignStore(tmp_path); saved = store.save(campaign())
    changed = copy.deepcopy(saved["document"])
    changed["opportunities"][0]["funding_tracking"]["requested"]["amount"] = value
    with pytest.raises(ValueError): store.save(changed, saved["id"], saved["revision"])
    assert store.get(saved["id"]) == saved


def test_legacy_exact_serialization_and_report_shape_are_unchanged(tmp_path):
    row = route(); del row["funding_tracking"]
    original = campaigns.validate(campaign(row))
    encoded = json.dumps(original, sort_keys=True).encode()
    before = hashlib.sha256(encoded).hexdigest()
    store = campaigns.CampaignStore(tmp_path); saved = store.save(original)
    reopened = store.get(saved["id"])["document"]
    assert "funding_tracking" not in reopened["opportunities"][0]
    assert hashlib.sha256(json.dumps(reopened, sort_keys=True).encode()).hexdigest() == before
    report = campaigns.prepare(reopened)
    assert "funding_summary" not in report and "Recorded funding totals" not in report["markdown"]


def test_save_reopen_export_import_and_stale_save_preserve_snapshots(tmp_path):
    store = campaigns.CampaignStore(tmp_path); saved = store.save(campaign())
    original = copy.deepcopy(saved)
    changed = copy.deepcopy(saved["document"])
    changed["opportunities"][0]["funding_tracking"]["target"] = amount("4500", "USD")
    changed["opportunities"][0]["funding_tracking"]["target"]["source_url"] = "https://example.invalid/receipt"
    updated = store.save(changed, saved["id"], saved["revision"])
    with pytest.raises(ValueError, match="changed"):
        store.save(original["document"], original["id"], original["revision"])
    assert campaigns.CampaignStore(tmp_path).get(saved["id"]) == updated
    backup = json.loads(json.dumps(updated["document"]))
    restored = store.save(backup)
    assert restored["id"] != saved["id"] and restored["document"] == updated["document"]
    assert store.get(saved["id"]) == updated


def test_adversarial_shape_broken_sources_and_control_chars_fail_closed():
    for key, value in (("round_key", "bad\x00key"), ("benefit_type", "money"),
                       ("requested", {"amount": "20", "source_id": "a" * 32}),
                       ("eligibility_evidence", {"source_url": "https://user:pass@example.invalid/"}),
                       ("unexpected", "silently lost")):
        row = route(); row["funding_tracking"][key] = value
        with pytest.raises(ValueError): campaigns.validate(campaign(row))


@pytest.mark.parametrize("traps", [True, False])
def test_exact_cent_arithmetic_independent_of_embedding_decimal_precision(traps):
    rows = [route("Fictional cents A", status="submitted", application="submitted"),
            route("Fictional cents B", status="submitted", application="submitted")]
    rows[0]["funding_tracking"]["requested"] = amount("999999999.99")
    rows[1]["funding_tracking"]["requested"] = amount("0.01")
    with localcontext() as context:
        context.prec = 2
        context.traps[InvalidOperation] = traps
        result = campaigns.funding_summary(campaign(*rows))
    assert group(result, "submitted")["total"] == "1000000000.00"


def test_tracking_notes_are_not_added_to_assistant_provider_context(tmp_path):
    row = route(); row.update(application_mode="required", applicant="Fictional Association", applicant_confirmed=True)
    row["funding_tracking"]["target"]["notes"] = "FICTIONAL TRACKING CANARY"
    store = campaigns.CampaignStore(tmp_path); saved = store.save(campaign(row))
    prepared = assistant.preview(store, {"id": saved["id"], "revision": saved["revision"],
        "opportunity": row["name"], "task": "enquiry", "question": "What is missing?", "checks": []})
    assert "FICTIONAL TRACKING CANARY" not in prepared["content"]
    assert "funding_tracking" not in prepared["content"]


def test_bounded_portfolio_admission_does_not_clip_or_create_extra_campaigns(tmp_path):
    rows = [{"name": f"Fictional round {index}", "status": "submitted"}
            for index in range(200)]
    store = campaigns.CampaignStore(tmp_path)
    saved = store.save(campaign(*rows))
    assert len(store.get(saved["id"])["document"]["opportunities"]) == 200
    assert len(store.list()) == 1
    summary = campaigns.funding_summary(saved["document"])
    assert summary["counts"]["opportunities"] == 200
    assert summary["counts"]["applications"] == {"submitted": 200}
    assert summary["stages"]["submitted"]["groups"][0]["unknown_amounts"] == 200
    oversized = copy.deepcopy(saved["document"])
    oversized["opportunities"].append({"name": "Fictional overflow"})
    with pytest.raises(ValueError, match="at most 200 opportunities"):
        store.save(oversized, saved["id"], saved["revision"])
    assert store.get(saved["id"]) == saved and len(store.list()) == 1


def test_ui_route_cli_and_programmatic_share_the_exact_totals(server, tmp_path, monkeypatch):
    document = campaign(); before = copy.deepcopy(document)
    direct = campaigns.funding_summary(document)
    with Runtime(tmp_path / "direct") as runtime:
        assert runtime.call("campaigns.funding_summary", {"document": document}) == direct
    status, _, body = post(server, "/api/campaigns/funding-summary", {"document": document})
    assert status == 200 and json.loads(body) == direct
    assert post(server, "/api/campaigns/funding-summary", {"document": document}, token=False)[0] == 403
    input_path = tmp_path / "input.json"; input_path.write_text(json.dumps({"document": document}), encoding="utf-8")
    output = io.StringIO()
    with patch("sys.stdout", output), patch("sys.argv", ["sinter", "run", "campaigns.funding_summary", "--input", str(input_path),
                    "--directory", str(tmp_path / "cli"), "--format", "json"]):
        cli.launch()
    envelope = json.loads(output.getvalue())
    assert envelope["ok"] and envelope["operation"] == "campaigns.funding_summary"
    assert envelope["result"] == direct and document == before
    assert campaigns.prepare(document)["funding_summary"] == direct
    assert any(item["id"] == "campaigns.funding_summary" for item in catalog()["operations"])
    human = io.StringIO()
    with patch("sys.stdout", human), patch("sys.argv", ["sinter", "run", "campaigns.funding_summary", "--input", str(input_path),
                    "--directory", str(tmp_path / "human")]):
        cli.launch()
    assert "Recorded funding totals" in human.getvalue()
    assert "Targets (1 round / record)" in human.getvalue()
