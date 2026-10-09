"""Check concise campaign guidance through the actual offline interface."""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import threading
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from sinter import client, practice  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    """Exercise distinct guidance, local navigation and untouched saved inputs."""
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    out = ROOT / "browser-artifacts" / "campaign-guidance"
    out.mkdir(parents=True, exist_ok=True)
    checks: list[str] = []
    errors: list[str] = []
    external: list[str] = []
    receipt = {
        "passed": False,
        "scope": "Local campaign guidance and navigation, not whole-product quality",
        "checks": checks,
        "page_errors": errors,
        "external_requests": external,
    }
    with tempfile.TemporaryDirectory(prefix="sinter-campaign-guidance-") as data:
        with patch.object(
            client,
            "_open",
            side_effect=AssertionError("Offline guidance attempted a hosted call"),
        ) as network:
            server = make_server(port=0, directory=data)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            garden = practice.garden()["campaign"]
            suggested = copy.deepcopy(garden)
            suggested["title"] = "Fictional suggested eligibility step"
            suggested["actions"] = []
            long_action = copy.deepcopy(garden)
            long_action["title"] = "Fictional long recorded action"
            full_task = (
                "Fictional operator check: " + "Keep the condition explicit. " * 15
            )
            long_action["actions"][1]["task"] = full_task
            ready = copy.deepcopy(garden)
            ready["title"] = "Fictional complete screening for human review"
            today = date.today().isoformat()
            source = ready["sources"][0]
            route = ready["opportunities"][0]
            source["checked_at"] = today
            route.update(
                status="open",
                application_mode="required",
                applicant="Fictional community association",
                applicant_confirmed=True,
                application_window="rolling",
                window_source_id=source["id"],
                window_source_url=source["url"],
                window_source_quote="Fictional practice applications are rolling.",
                window_checked_at=today,
            )
            ready["requirements"] = [
                {
                    "opportunity": route["name"],
                    "rule": "Fictional applicant condition",
                    "status": "met",
                    "evidence": "Fictional applicant record checked by the user.",
                    "source_id": source["id"],
                    "source_url": source["url"],
                    "source_quote": "Fictional associations may apply in this example.",
                    "checked_at": today,
                }
            ]
            submitted = copy.deepcopy(ready)
            submitted["title"] = "Fictional submitted route"
            submitted["opportunities"][0]["status"] = "submitted"
            inactive = copy.deepcopy(garden)
            inactive["title"] = "Fictional inactive route"
            for opportunity in inactive["opportunities"]:
                opportunity["status"] = "closed"
            evidence_cases: list[tuple[dict, int, str, str]] = []
            for label, age, state, count, guidance, verdict in [
                ("fresh", 0, "HUMAN REVIEW REQUIRED", 0, "", "met"),
                ("90 days", 90, "HUMAN REVIEW REQUIRED", 0, "", "met"),
                ("91 days", 91, "NOT READY", 1, "last checked 91 days ago", "met"),
                ("future", -1, "NOT READY", 1, "is in the future", "met"),
                ("changed source", 0, "NOT READY", 1,
                 "saved check date differs from the linked record", "met"),
                ("recorded unmet", 0, "NOT READY", 0,
                 "marked not met in the user-entered record", "not_met"),
            ]:
                fixture = copy.deepcopy(ready)
                fixture["title"] = "Fictional requirement evidence — " + label
                fixture["actions"] = []
                check_date = (date.today() - timedelta(days=age)).isoformat()
                evidence_source = {
                    "id": "e" * 32,
                    "title": "Fictional applicant evidence source",
                    "url": "https://example.invalid/applicant-rules",
                    "notes": "Fictional browser fixture; no real applicant or programme.",
                    "checked_at": (
                        (date.today() - timedelta(days=1)).isoformat()
                        if label == "changed source" else check_date
                    ),
                }
                # Window evidence remains fresh: only this requirement's saved
                # evidence date/snapshot varies, so the visible count is scoped.
                fixture["sources"].append(evidence_source)
                fixture["requirements"][0].update(
                    source_id=evidence_source["id"],
                    source_url=evidence_source["url"],
                    checked_at=check_date,
                    status=verdict,
                )
                evidence_cases.append((fixture, count, state, guidance))
            business_ready = copy.deepcopy(ready)
            business_ready["title"] = "Fictional research company human review"
            business_ready["organisation"] = "Fictional Research Company"
            business_ready["opportunities"][0]["applicant"] = (
                "Fictional Research Company"
            )
            business_ready["actions"] = []
            saved = [
                server.app.campaigns.save(item)
                for item in [
                    suggested, long_action, ready, submitted, inactive,
                    *[case[0] for case in evidence_cases], business_ready,
                ]
            ]
            try:
                with sync_playwright() as driver:
                    browser = launch_chromium(driver, args.chromium)
                    context = browser.new_context(
                        viewport={"width": 1440, "height": 1000},
                        reduced_motion="reduce",
                    )
                    context.route(
                        "**/*",
                        lambda route: (
                            route.continue_()
                            if route.request.url.startswith(base + "/")
                            else (external.append(route.request.url), route.abort())
                        ),
                    )
                    page = context.new_page()
                    page.set_default_timeout(7000)
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.on("dialog", lambda dialog: dialog.accept())
                    page.goto(base + "/#home")
                    page.get_by_role(
                        "region", name="Fictional garden practice project"
                    ).get_by_role(
                        "button", name="Open garden campaign", exact=True
                    ).click()
                    card = page.get_by_role(
                        "region", name="Campaign decision and next move"
                    )
                    expect(card).to_be_visible()
                    blocker = (
                        "Record a current official source link and a source excerpt. "
                        "Record the date this eligibility source was checked."
                    )
                    assert card.inner_text().count(blocker) == 1
                    assert card.inner_text().count("Sinter has not verified") == 1
                    expect(card.locator(".campaign-decision-reopen")).to_contain_text(
                        "After resolving the blocker above"
                    )
                    expect(
                        card.locator(".campaign-decision-reopen")
                    ).not_to_contain_text("Confirm applicant conditions and exclusions")
                    expect(card.locator("[data-state='not_ready']")).to_have_text(
                        "NOT READY"
                    )
                    card.screenshot(path=str(out / "garden-distinct-guidance.png"))
                    checks.append(
                        "garden shows one concrete blocker, one shared qualification "
                        "and distinct progress criteria while remaining NOT READY"
                    )
                    expect(card.locator(".campaign-decision-owner")).to_contain_text(
                        "Confirm whether this entry is a named person "
                        "or a suggested role"
                    )
                    expect(card.locator(".campaign-decision-date")).to_contain_text(
                        "Proposed target:"
                    )
                    card.get_by_role(
                        "button", name="Open full action", exact=True
                    ).click()
                    action = page.locator(
                        "[data-action-index='1'] [data-campaign-field='task']"
                    )
                    expect(action).to_have_value(garden["actions"][1]["task"])
                    pending_task = (
                        garden["actions"][1]["task"] + " — local unsaved note"
                    )
                    action.fill(pending_task)
                    card.get_by_role(
                        "button", name="Review route checks", exact=True
                    ).click()
                    expect(
                        page.get_by_role("tab", name="Opportunities", exact=True)
                    ).to_have_attribute("aria-selected", "true")
                    assert page.evaluate(
                        "document.activeElement.classList.contains('campaign-focus')"
                    )
                    expect(
                        page.get_by_role("region", name="Selected opportunity")
                    ).to_contain_text("Confirm applicant conditions and exclusions")
                    checks.append(
                        "recorded full action and owner/date conditions remain "
                        "accessible; review control opens and focuses selected route"
                    )
                    card.get_by_role(
                        "button", name="Open full action", exact=True
                    ).click()
                    expect(action).to_have_value(pending_task)
                    expect(page.locator(".campaign-save-state")).to_have_text(
                        "Unsaved changes"
                    )
                    action.fill(garden["actions"][1]["task"])
                    checks.append(
                        "route-check navigation preserves an unsaved local action "
                        "edit without saving or replacing it"
                    )

                    def open_saved(title: str) -> None:
                        page.get_by_role(
                            "button", name="Open " + title, exact=True
                        ).click()
                        expect(
                            page.locator("[data-campaign-field='title']")
                        ).to_have_value(title)

                    open_saved(suggested["title"])
                    expect(card.locator(".campaign-decision-task")).to_have_text(
                        "Start with the blocker in Selected route status."
                    )
                    assert card.inner_text().count(blocker) == 1
                    assert card.inner_text().count("Sinter has not verified") == 1
                    expect(card.locator(".campaign-decision-date")).to_have_count(0)
                    expect(card.locator(".campaign-decision-owner")).to_contain_text(
                        "Owner needed"
                    )
                    page.get_by_role("tab", name="Next actions", exact=True).click()
                    card.get_by_role(
                        "button", name="Review route checks", exact=True
                    ).click()
                    expect(
                        page.get_by_role("tab", name="Opportunities", exact=True)
                    ).to_have_attribute("aria-selected", "true")
                    card.screenshot(path=str(out / "suggested-step-deduplicated.png"))
                    checks.append(
                        "suggested step points to its already visible blocker "
                        "without fabricating an owner or date; "
                        "control returns to checks"
                    )
                    open_saved(long_action["title"])
                    card.get_by_role(
                        "button", name="Open full action", exact=True
                    ).click()
                    expect(
                        page.locator(
                            "[data-action-index='1'] [data-campaign-field='task']"
                        )
                    ).to_have_value(full_task)
                    checks.append(
                        "long recorded action stays intact in Next actions "
                        "despite its short card preview"
                    )
                    open_saved(ready["title"])
                    expect(card.locator(".campaign-decision-state")).to_have_text(
                        "HUMAN REVIEW REQUIRED"
                    )
                    assert card.inner_text().count("Sinter has not verified") == 1
                    expect(card).to_contain_text("not permission to submit")
                    expect(card.locator(".campaign-decision-reopen")).to_contain_text(
                        "authority appropriate to this campaign before any submission"
                    )
                    checks.append(
                        "complete user-entered screening still requires human "
                        "review and explicit authority before submission"
                    )
                    requirement_count = page.locator(".campaign-summary > div").filter(
                        has=page.locator("span", has_text="requirements to check")
                    ).locator("strong")
                    for fixture, count, state, guidance in evidence_cases:
                        open_saved(fixture["title"])
                        expect(requirement_count).to_have_text(str(count))
                        expect(card.locator(".campaign-decision-state")).to_have_text(
                            state
                        )
                        if guidance:
                            expect(card.locator(".campaign-decision-detail")).to_contain_text(
                                guidance
                            )
                        else:
                            expect(card.locator(".campaign-decision-detail")).to_contain_text(
                                "complete user-entered screening records"
                            )
                        expect(page.locator(".campaign-save-state")).to_have_text(
                            "Saved on this computer"
                        )
                        checks.append(
                            fixture["title"] + ": visible requirement count "
                            "agrees with decision evidence policy; original "
                            "verdict and source snapshot remain saved"
                        )
                    open_saved(business_ready["title"])
                    expect(requirement_count).to_have_text("0")
                    expect(card.locator(".campaign-decision-state")).to_have_text(
                        "HUMAN REVIEW REQUIRED"
                    )
                    expect(card.locator(".campaign-decision-task")).to_contain_text(
                        "Ask a campaign reviewer"
                    )
                    expect(card.locator(".campaign-decision-reopen")).to_contain_text(
                        "authority appropriate to this campaign"
                    )
                    expect(card.locator(".campaign-decision-task")).not_to_contain_text(
                        "P&C"
                    )
                    expect(card.locator(".campaign-decision-date")).to_have_count(0)
                    card.screenshot(path=str(out / "business-neutral-reviewer.png"))
                    checks.append(
                        "business review guidance retains eligibility and authority "
                        "checks without inventing a P&C reviewer or target date"
                    )
                    open_saved(submitted["title"])
                    expect(card.locator(".campaign-decision-state")).to_have_text(
                        "AWAITING FUNDER DECISION"
                    )
                    expect(card).to_contain_text("not an award or a rejection")
                    assert card.inner_text().count("Sinter has not verified") == 1
                    checks.append(
                        "submitted status remains awaiting decision and is "
                        "never interpreted as an award or rejection"
                    )
                    open_saved(inactive["title"])
                    expect(card.locator(".campaign-decision-state")).to_have_text(
                        "NO-GO FOR NOW"
                    )
                    expect(card.locator(".campaign-decision-reopen")).to_contain_text(
                        "funder publishes a future round"
                    )
                    assert card.inner_text().count("Sinter has not verified") == 1
                    expect(card.locator(".campaign-decision-date")).to_have_count(0)
                    checks.append(
                        "inactive route remains no-go with evidence-led "
                        "future-round conditions and no revived target date"
                    )
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth"
                    )
                    checks.append("guidance fits a narrow viewport without overflow")
                    for original in saved:
                        assert server.app.campaigns.get(original["id"]) == original
                    checks.append(
                        "all saved source snapshots, historical entries, "
                        "action ownership and dates remain unchanged"
                    )
                    assert not errors, errors
                    assert not external, external
                    network.assert_not_called()
                    browser.close()
                    receipt["passed"] = True
            finally:
                server.shutdown()
                server.server_close()
                server.app.close()
                thread.join(timeout=5)
                receipt.update(
                    {
                        "source_sha256": {
                            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
                            for name in [
                                "src/sinter/web/campaign-decision.js",
                                "src/sinter/web/campaign-requirement-policy.js",
                                "src/sinter/web/campaign-source-state.js",
                                "src/sinter/web/campaigns.js",
                            ]
                        },
                        "server_stopped": not thread.is_alive(),
                        "browser_closed": True,
                        "hosted_calls": 0,
                    }
                )
                (out / "browser-receipt.json").write_text(
                    json.dumps(receipt, indent=2) + "\n"
                )
    print(f"PASS: {len(checks)} campaign guidance journeys. No hosted calls.")


if __name__ == "__main__":
    main()
