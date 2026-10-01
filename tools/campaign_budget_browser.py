"""Fictional quoted-budget journeys through the real local server and browser.

Checks compact costs, exact cents, original-value preservation, current and
historical answer reviews, keyboard focus, phone layout and report/Word holds.
No real workspace or supplier record is opened; all provider calls and external
browser requests are blocked. Each run retains a separate evidence directory.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import threading
import time
import zipfile
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch
from xml.etree import ElementTree as ET

if TYPE_CHECKING:
    from playwright.sync_api import Locator, Page, Route

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from sinter import client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402
from tools.campaign_browser import CampaignChecks  # noqa: E402


def source_hashes() -> dict[str, str]:
    """Bind a receipt to all implementation source bytes before and after work."""
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT / "src").rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def main(
    argv: Sequence[str] | None = None, *, require_safe_reports: bool = True
) -> dict:
    """Run the shipped report-safety gate; private UI review may hold that gate."""
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifacts = ROOT / "browser-artifacts"
    artifacts.mkdir(exist_ok=True)
    ART = Path(tempfile.mkdtemp(prefix="campaign-budget-", dir=artifacts))
    source_before = source_hashes()
    ROUTE = "Fictional application fund"
    ALT = "Fictional second fund"
    HIST = "Fictional archived fund"
    ORIGINAL = {
        "schema": "sinter-campaign/v1",
        "title": "Fictional compact quote budget",
        "organisation": "Fictional Workshop Association",
        "objective": (
            "Record original quotes and unknown production "
            "costs; manual application amounts are not "
            "available."
        ),
        "opportunities": [
            {
                "name": name,
                "funder": "Fictional Fund",
                "url": "https://example.invalid/fund",
                "deadline": "",
                "decision_window": "Unknown",
                "ceiling": "200.00",
                "fit": "Fictional application basis unknown",
                "status": "researching",
                "application_mode": "required",
                "applicant": "Fictional Workshop Association",
                "applicant_confirmed": True,
            }
            for name in [ROUTE, ALT]
        ],
        "budget": [
            {
                "item": "Fictional prototype material",
                "opportunity": ROUTE,
                "quantity": 1,
                "unit_cost": "110.00",
                "quote_reference": (
                    "Fictional Quote A: AUD 110.00 including GST. "
                    "Original wording retained exactly; "
                    "financial_semantics unknown."
                ),
            },
            {
                "item": "Fictional finishing work",
                "opportunity": ROUTE,
                "quantity": 1,
                "unit_cost": "100.00",
                "quote_reference": (
                    "Fictional Quote B: AUD 100.00 excluding GST. "
                    "Original wording retained exactly; "
                    "financial_semantics unknown."
                ),
            },
            {
                "item": "Fictional production cost unknown",
                "opportunity": ROUTE,
                "quantity": 1,
                "unit_cost": None,
                "quote_reference": "",
            },
        ],
        "answers": [
            {
                "opportunity": ROUTE,
                "label": "Fictional project purpose",
                "text": "Fictional answer previously reviewed by a person.",
                "limit": 300,
                "status": "reviewed",
            }
        ],
        "requirements": [],
        "actions": [],
        "sources": [],
    }
    ORIGINAL["opportunities"].append(
        {
            "name": HIST,
            "funder": "Fictional Archived Fund",
            "url": "https://example.invalid/archived",
            "deadline": "",
            "decision_window": "Unknown",
            "ceiling": None,
            "fit": "Historical evidence only",
            "status": "closed",
            "application_mode": "required",
            "applicant": "Fictional Workshop Association",
            "applicant_confirmed": True,
        }
    )
    ORIGINAL["answers"].extend(
        [
            {
                "opportunity": ALT,
                "label": "Second current answer",
                "text": "Fictional second application answer",
                "limit": 300,
                "status": "reviewed",
            },
            {
                "opportunity": HIST,
                "label": "Archived answer",
                "text": (
                    "Fictional historical answer; old review is "
                    "preserved as historical only"
                ),
                "limit": 300,
                "status": "reviewed",
            },
        ]
    )
    ORIGINAL["budget"].append(
        {
            "item": "Fictional historical cost",
            "opportunity": HIST,
            "quantity": 1,
            "unit_cost": "10.00",
            "quote_reference": (
                "Fictional old quote; retained as historical evidence only"
            ),
        }
    )
    (ART / "input-original.json").write_text(json.dumps(ORIGINAL, indent=2) + "\n")
    receipt = {
        "schema": "sinter-independent-quoted-budget-ui-review/v1",
        "source_sha256_before": source_before,
        "scope": "Combined quoted-budget UI and source-only report safety"
        if require_safe_reports
        else "Private UI-only producer verification; backend is not qualified.",
        "checks": [],
        "negative_findings": [],
        "browser_errors": [],
        "external_requests": [],
        "resources": {
            "browser_closed": False,
            "context_closed": False,
            "server_closed": False,
            "server_thread_stopped": False,
        },
        "report_safety_required": require_safe_reports,
        "latency": {},
        "screenshots": [],
    }

    def check(name: str, condition: object, detail: object = None) -> None:
        receipt["checks"].append(
            {"check": name, "passed": bool(condition), "detail": detail}
        )
        if not condition:
            receipt["negative_findings"].append({"check": name, "detail": detail})

    def shot(page: Page, name: str, full: bool = False) -> None:
        path = ART / (name + ".png")
        page.screenshot(path=str(path), full_page=full, animations="disabled")
        receipt["screenshots"].append(path.name)

    def backup(page: Page, checks: CampaignChecks, name: str) -> dict:
        checks.transfers(page)
        with page.expect_download() as pending:
            page.get_by_role(
                "button", name="Export campaign backup", exact=True
            ).click()
        path = ART / (name + ".json")
        pending.value.save_as(str(path))
        return json.loads(path.read_text())

    def open_states(page: Page) -> list[bool]:
        return page.locator(".campaign-budget-row>details").evaluate_all(
            "(els)=>els.map(el=>el.open)"
        )

    def focus_state(page: Page) -> dict:
        return page.evaluate(
            """() => {
              const el = document.activeElement;
              const r = el.getBoundingClientRect();
              return {field: el.dataset.campaignField || '',
                row: el.closest('[data-budget-index]')?.dataset.budgetIndex,
                top: r.top, bottom: r.bottom, left: r.left, right: r.right,
                height: innerHeight, width: innerWidth};
            }"""
        )

    with (
        tempfile.TemporaryDirectory(prefix="sinter-ui-independent-fictional-") as data,
        ExitStack() as guard,
    ):
        for name in ["chat", "search", "_post", "_get", "_open"]:
            guard.enter_context(
                patch.object(
                    client,
                    name,
                    side_effect=AssertionError("Unexpected remote " + name),
                )
            )
        server = make_server(port=0, directory=data)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as pw:
                browser = launch_chromium(pw, args.chromium)
                base = f"http://127.0.0.1:{server.server_port}"
                context = browser.new_context(
                    viewport={"width": 1440, "height": 1000},
                    accept_downloads=True,
                    reduced_motion="reduce",
                    permissions=["clipboard-read", "clipboard-write"],
                )

                def guard_url(route: Route) -> None:
                    if route.request.url.startswith(base + "/"):
                        route.continue_()
                    else:
                        receipt["external_requests"].append(route.request.url)
                        route.abort()

                context.route("**/*", guard_url)
                page = context.new_page()
                page.set_default_timeout(8000)
                page.on(
                    "pageerror", lambda err: receipt["browser_errors"].append(str(err))
                )
                page.on(
                    "console",
                    lambda m: (
                        receipt["browser_errors"].append(m.text)
                        if m.type == "error"
                        else None
                    ),
                )
                page.on("dialog", lambda d: d.accept())
                checks = CampaignChecks(browser, base, ART)

                def seed(document: dict | None = None) -> None:
                    checks.import_fixture(page, copy.deepcopy(document or ORIGINAL))
                    page.get_by_role("tab", name="Budget", exact=True).click()

                def row(index: int) -> Locator:
                    return page.locator(f'[data-budget-index="{index}"]')

                def open_row(index: int) -> None:
                    if row(index).locator("details").get_attribute("open") is None:
                        row(index).locator("summary").click()

                try:
                    t = time.perf_counter()
                    seed()
                    receipt["latency"]["initial_import_and_budget_ms"] = round(
                        (time.perf_counter() - t) * 1000, 3
                    )
                    expect(page.locator(".campaign-budget-total")).to_have_text(
                        (
                            "Recorded quoted subtotal (AUD): A$210.00 · 1 "
                            "uncosted item — total incomplete"
                        )
                    )
                    check(
                        "first-missing-cost-auto-open",
                        open_states(page) == [False, False, True, False],
                        open_states(page),
                    )
                    check(
                        "quote-basis-note-visible",
                        "No GST conversion was made."
                        in page.locator(".campaign-budget-basis-note").inner_text(),
                    )
                    check(
                        "collapsed-priced-summary-contains-amount",
                        row(0).locator("summary").inner_text().find("A$110.00") >= 0,
                    )
                    shot(page, "desktop-initial-full", True)
                    page.get_by_role(
                        "heading", name="Current project costs", exact=True
                    ).evaluate('(el)=>el.scrollIntoView({block:"center"})')
                    shot(page, "desktop-compact-budget")
                    t = time.perf_counter()
                    page.get_by_role(
                        "button", name="Open the next cost to check", exact=True
                    ).click()
                    expect(
                        row(2).get_by_label("Unit cost (AUD)", exact=True)
                    ).to_be_focused()
                    receipt["latency"]["next-price-focus_ms"] = round(
                        (time.perf_counter() - t) * 1000, 3
                    )
                    check(
                        "next-focus-price",
                        focus_state(page)["field"] == "unit_cost",
                        focus_state(page),
                    )
                    row(2).get_by_label("Unit cost (AUD)", exact=True).fill("0")
                    expect(page.locator(".campaign-budget-total")).to_have_text(
                        "Recorded quoted subtotal (AUD): A$210.00"
                    )
                    check(
                        "zero-is-priced-not-unknown",
                        "A$0.00" in row(2).locator("summary").inner_text(),
                    )
                    page.get_by_role(
                        "button", name="Open the next cost to check", exact=True
                    ).click()
                    expect(
                        row(2).get_by_label("Quote or estimate reference", exact=True)
                    ).to_be_focused()
                    check(
                        "next-focus-missing-reference",
                        focus_state(page)["field"] == "quote_reference",
                        focus_state(page),
                    )
                    row(2).get_by_label("Quote or estimate reference", exact=True).fill(
                        "Fictional zero estimate; amount semantics unreviewed."
                    )
                    check(
                        "next-hidden-after-all-priced-and-referenced",
                        page.get_by_role(
                            "button", name="Open the next cost to check", exact=True
                        ).is_hidden(),
                    )
                    open_row(1)
                    row(1).get_by_label("Unit cost (AUD)", exact=True).fill("0.10")
                    row(1).get_by_label("Quantity", exact=True).fill("3")
                    expect(page.locator(".campaign-budget-total")).to_have_text(
                        "Recorded quoted subtotal (AUD): A$110.30"
                    )
                    check("integer-cents-after-edit", True)
                    for width in [390, 320]:
                        seed()
                        page.set_viewport_size({"width": width, "height": 844})
                        page.get_by_role(
                            "heading", name="Current project costs", exact=True
                        ).evaluate('(el)=>el.scrollIntoView({block:"center"})')
                        shot(page, f"phone-{width}-compact-budget")
                        check(
                            f"phone-{width}-no-horizontal-overflow",
                            page.evaluate(
                                "()=>document.documentElement.scrollWidth<=innerWidth+1"
                            ),
                        )
                        page.get_by_role(
                            "button", name="Open the next cost to check", exact=True
                        ).click()
                        f = focus_state(page)
                        check(
                            f"phone-{width}-price-focus-visible",
                            f["field"] == "unit_cost"
                            and f["top"] >= 0
                            and f["bottom"] <= f["height"],
                            f,
                        )
                        shot(page, f"phone-{width}-next-price-focus")
                        summary = row(0).locator("summary")
                        summary.focus()
                        page.keyboard.press("Enter")
                        expect(
                            row(0).get_by_label("Unit cost (AUD)", exact=True)
                        ).to_be_visible()
                        page.keyboard.press("Space")
                        check(
                            f"phone-{width}-summary-keyboard-toggle",
                            row(0)
                            .get_by_label("Unit cost (AUD)", exact=True)
                            .is_hidden(),
                        )
                        page.set_viewport_size({"width": 1440, "height": 1000})
                    seed()
                    row(2).locator("summary").click()
                    row(0).locator("summary").click()
                    before = open_states(page)
                    t = time.perf_counter()
                    checks.save(page)
                    receipt["latency"]["save_ms"] = round(
                        (time.perf_counter() - t) * 1000, 3
                    )
                    check(
                        "save-preserves-open-and-collapsed-state",
                        open_states(page) == before,
                        {"before": before, "after": open_states(page)},
                    )
                    retained = backup(page, checks, "save-backup")
                    check(
                        "save-backup-originals-exact",
                        retained["budget"] == ORIGINAL["budget"],
                    )
                    page.reload()
                    checks.goto(page, "campaigns")
                    page.get_by_role("tab", name="Budget", exact=True).click()
                    reopened = backup(page, checks, "reopened-backup")
                    check(
                        "reopen-backup-originals-exact",
                        reopened["budget"] == ORIGINAL["budget"],
                    )
                    check(
                        "reopen-first-missing-auto-open",
                        open_states(page) == [False, False, True, False],
                        open_states(page),
                    )
                    # Start each mutation with reviewed answers and a current preview.
                    for name in [
                        "add",
                        "item-name",
                        "price",
                        "quantity",
                        "allocation",
                        "reference",
                        "remove",
                    ]:
                        seed()
                        page.get_by_role(
                            "button", name="Prepare campaign brief", exact=True
                        ).click()
                        expect(
                            page.get_by_role("region", name="Your draft report")
                        ).to_be_visible()
                        page.get_by_role("tab", name="Budget", exact=True).click()
                        open_row(0)
                        if name == "add":
                            page.get_by_role(
                                "button", name="Add budget item", exact=True
                            ).click()
                        elif name == "item-name":
                            row(0).get_by_label("Budget item", exact=True).fill(
                                "Fictional material purpose changed"
                            )
                        elif name == "price":
                            row(0).get_by_label("Unit cost (AUD)", exact=True).fill(
                                "111.00"
                            )
                        elif name == "quantity":
                            row(0).get_by_label("Quantity", exact=True).fill("2")
                        elif name == "allocation":
                            row(0).get_by_label(
                                "Funding opportunity", exact=True
                            ).select_option(ALT)
                        elif name == "reference":
                            row(0).get_by_label(
                                "Quote or estimate reference", exact=True
                            ).fill("Fictional updated source; basis still unknown.")
                        else:
                            row(0).get_by_role(
                                "button", name="Remove budget item", exact=True
                            ).click()
                        immediate_focus = focus_state(page)
                        captured = backup(page, checks, "mutation-" + name)
                        check(
                            name + "-marks-active-answer-drafts",
                            all(
                                a["status"] == "draft" for a in captured["answers"][:2]
                            ),
                            {
                                "observed_answer_statuses": [
                                    a["status"] for a in captured["answers"]
                                ]
                            },
                        )
                        check(
                            name + "-preserves-historical-answer-review",
                            captured["answers"][2]["status"] == "reviewed",
                            {
                                "observed_answer_statuses": [
                                    a["status"] for a in captured["answers"]
                                ]
                            },
                        )
                        check(
                            name + "-marks-preview-stale",
                            page.locator("#campaign-output").get_attribute("data-stale")
                            == "true",
                        )
                        check(
                            name + "-preview-controls-disabled",
                            page.locator("#campaign-output .report-area").get_attribute(
                                "inert"
                            )
                            is not None,
                        )
                        if name == "add":
                            check(
                                "add-focuses-title",
                                immediate_focus["field"] == "item",
                                immediate_focus,
                            )
                    for name in [
                        "item-name",
                        "price",
                        "quantity",
                        "reference",
                        "allocation-active",
                        "allocation-whole",
                    ]:
                        seed()
                        open_row(3)
                        if name == "item-name":
                            row(3).get_by_label("Budget item", exact=True).fill(
                                "Fictional revised historical label"
                            )
                        elif name == "price":
                            row(3).get_by_label("Unit cost (AUD)", exact=True).fill(
                                "12.00"
                            )
                        elif name == "quantity":
                            row(3).get_by_label("Quantity", exact=True).fill("2")
                        elif name == "reference":
                            row(3).get_by_label(
                                "Quote or estimate reference", exact=True
                            ).fill(
                                "Fictional updated historical quote; still historical."
                            )
                        elif name == "allocation-active":
                            row(3).get_by_label(
                                "Funding opportunity", exact=True
                            ).select_option(ROUTE)
                        else:
                            row(3).get_by_label(
                                "Funding opportunity", exact=True
                            ).select_option("")
                        captured = backup(page, checks, "historical-mutation-" + name)
                        actual = [a["status"] for a in captured["answers"]]
                        expected = (
                            ["draft", "draft", "reviewed"]
                            if name.startswith("allocation-")
                            else ["reviewed", "reviewed", "reviewed"]
                        )
                        check(
                            "historical-" + name + "-review-status-boundary",
                            actual == expected,
                            {"actual": actual, "expected": expected},
                        )
                    seed()
                    page.get_by_role(
                        "button", name="Prepare campaign brief", exact=True
                    ).click()
                    expect(
                        page.get_by_role("region", name="Your draft report")
                    ).to_be_visible()
                    page.get_by_role("tab", name="Budget", exact=True).click()
                    open_row(3)
                    row(3).get_by_role(
                        "button", name="Remove budget item", exact=True
                    ).click()
                    captured = backup(page, checks, "historical-delete")
                    check(
                        "historical-delete-preserves-all-review-flags",
                        [a["status"] for a in captured["answers"]]
                        == ["reviewed", "reviewed", "reviewed"],
                    )
                    check(
                        "historical-delete-preserves-current-budget-originals",
                        captured["budget"] == ORIGINAL["budget"][:3],
                    )
                    check(
                        "historical-delete-stales-preview",
                        page.locator("#campaign-output").get_attribute("data-stale")
                        == "true",
                    )
                    for name in ["empty", "missing"]:
                        scope_fixture = copy.deepcopy(ORIGINAL)
                        if name == "empty":
                            scope_fixture["budget"][0]["opportunity"] = ""
                        else:
                            scope_fixture["budget"][0].pop("opportunity")
                        seed(scope_fixture)
                        open_row(0)
                        row(0).get_by_label(
                            "Quote or estimate reference", exact=True
                        ).fill(
                            "Fictional revised whole-campaign quote; semantics unknown."
                        )
                        captured = backup(page, checks, "scope-" + name)
                        check(
                            "scope-" + name + "-normalized-whole-campaign",
                            captured["budget"][0]["opportunity"] == "",
                        )
                        check(
                            "scope-" + name + "-drafts-active-only",
                            [a["status"] for a in captured["answers"]]
                            == ["draft", "draft", "reviewed"],
                        )
                    seed()
                    with page.expect_response(
                        lambda response: (
                            response.url.endswith("/api/campaigns/prepare")
                            and response.request.method == "POST"
                        )
                    ) as prepared:
                        page.get_by_role(
                            "button", name="Prepare campaign brief", exact=True
                        ).click()
                    expect(
                        page.get_by_role("region", name="Your draft report")
                    ).to_be_visible()
                    source_report = prepared.value.json()
                    (ART / "source-only-report.json").write_text(
                        json.dumps(source_report, indent=2) + "\n"
                    )
                    report_region = page.get_by_role("region", name="Your draft report")
                    with page.expect_download() as word_download:
                        report_region.get_by_role(
                            "button", name="Download Word brief (.docx)", exact=True
                        ).click()
                    word_download.value.save_as(str(ART / "source-only-report.docx"))
                    with zipfile.ZipFile(ART / "source-only-report.docx") as word:
                        xml = ET.fromstring(word.read("word/document.xml"))
                        word_text = "\n".join(
                            node.text or ""
                            for node in xml.findall(
                                (
                                    ".//{http://schemas.openxmlformats.org/wordproces"
                                    "singml/2006/main}t"
                                )
                            )
                        )
                    (ART / "word-visible-text.txt").write_text(word_text)
                    summary = source_report["budget_summary"]
                    readiness = source_report["readiness"]
                    receipt["report_boundary_observations"] = {
                        "budget_summary": summary,
                        "readiness": readiness,
                        "word_text": word_text,
                    }
                    check(
                        "source-only-report-original-budget-values-exact",
                        source_report["campaign"]["budget"] == ORIGINAL["budget"],
                    )
                    if require_safe_reports:
                        check(
                            "source-only-report-amount-basis-note",
                            isinstance(summary.get("amount_basis_note"), str)
                            and "GST" in summary["amount_basis_note"]
                            and "not an eligibility or application-ceiling decision"
                            in summary["amount_basis_note"],
                            summary.get("amount_basis_note"),
                        )
                        check(
                            "source-only-report-quoted-subtotal-exact",
                            summary.get("known_total") == "210.00"
                            and summary.get("total") is None
                            and summary.get("unknown_costs") == 1,
                            summary,
                        )
                        check(
                            "source-only-report-ceiling-verdict-held",
                            all(
                                "over_ceiling" in group
                                and group["over_ceiling"] is None
                                and group.get("amount_basis_note")
                                == summary.get("amount_basis_note")
                                for group in summary["by_opportunity"]
                            ),
                            summary.get("by_opportunity"),
                        )
                        group = next(
                            row
                            for row in summary["by_opportunity"]
                            if row["opportunity"] == ROUTE
                        )
                        check(
                            "source-only-report-raw-quoted-subtotal-observation",
                            group.get("quoted_subtotal_over_ceiling") is True,
                            group,
                        )
                        check(
                            "source-only-report-separate-readiness-counts",
                            readiness.get("budget_amount_basis_review") == 1
                            and readiness.get("unknown_costs") == 1
                            and readiness.get("budgets_over_ceiling") == 0
                            and readiness.get("quoted_subtotals_above_ceiling") == 1,
                            readiness,
                        )
                        check(
                            "word-no-qualified-raw-ceiling-verdict",
                            "exceeds the entered funding ceiling" not in word_text
                            and "over the funding ceiling" not in word_text,
                            word_text,
                        )
                        check(
                            "word-contains-amount-basis-hold",
                            "GST" in word_text
                            and "application amount" in word_text
                            and "quoted subtotal" in word_text.lower(),
                            word_text,
                        )
                    seed()
                    initial = backup(page, checks, "nonmutating-before")
                    page.get_by_role("tab", name="Budget", exact=True).focus()
                    page.keyboard.press("ArrowRight")
                    page.keyboard.press("ArrowLeft")
                    row(0).locator("summary").focus()
                    page.keyboard.press("Enter")
                    page.keyboard.press("Space")
                    checks.save(page)
                    unchanged = backup(page, checks, "nonmutating-after-save")
                    check(
                        "navigation-toggle-save-do-not-change-reviews",
                        [a["status"] for a in unchanged["answers"]]
                        == [a["status"] for a in initial["answers"]],
                    )
                    page.reload()
                    checks.goto(page, "campaigns")
                    page.get_by_role("tab", name="Budget", exact=True).click()
                    unchanged = backup(page, checks, "nonmutating-after-reopen")
                    check(
                        "reopen-does-not-change-reviews",
                        [a["status"] for a in unchanged["answers"]]
                        == [a["status"] for a in initial["answers"]],
                    )
                    calculation = page.evaluate(
                        """async rows => {
                          const {campaignQuotedBudget} = await import(
                            '/static/campaign-budget.js');
                          return {label: campaignQuotedBudget(rows).label};
                        }""",
                        ORIGINAL["budget"],
                    )
                    unchanged = backup(page, checks, "nonmutating-after-calculation")
                    check(
                        "pure-calculation-does-not-change-reviews",
                        [a["status"] for a in unchanged["answers"]]
                        == [a["status"] for a in initial["answers"]],
                        calculation,
                    )
                    seed()
                    page.get_by_role(
                        "button", name="Prepare campaign brief", exact=True
                    ).click()
                    expect(
                        page.get_by_role("region", name="Your draft report")
                    ).to_be_visible()
                    page.get_by_role("tab", name="Budget", exact=True).click()
                    row(0).locator("summary").focus()
                    page.keyboard.press("Enter")
                    check(
                        "view-toggle-does-not-stale-preview",
                        page.locator("#campaign-output").get_attribute("data-stale")
                        != "true",
                    )
                    seed(
                        {
                            "schema": "sinter-campaign/v1",
                            "title": "Fictional empty budget",
                            "organisation": "Fictional Association",
                            "objective": "No original quote recorded",
                            "opportunities": [],
                            "budget": [],
                        }
                    )
                    check(
                        "empty-budget-total-unknown",
                        "total is unknown"
                        in page.locator(".campaign-budget-total").inner_text(),
                    )
                    zero = copy.deepcopy(ORIGINAL)
                    zero["budget"] = [
                        {
                            "item": "Fictional zero cost",
                            "opportunity": ROUTE,
                            "quantity": 2,
                            "unit_cost": "0.00",
                            "quote_reference": "Fictional zero estimate",
                        }
                    ]
                    seed(zero)
                    expect(page.locator(".campaign-budget-total")).to_have_text(
                        "Recorded quoted subtotal (AUD): A$0.00"
                    )
                    check("zero-only-total-exact", True)
                    seed()
                    open_row(0)
                    row(0).get_by_label("Budget item", exact=True).fill("Q" * 1000)
                    page.set_viewport_size({"width": 320, "height": 844})
                    check(
                        "phone320-long-title-no-horizontal-overflow",
                        page.evaluate(
                            "()=>document.documentElement.scrollWidth<=innerWidth+1"
                        ),
                    )
                    page.evaluate(
                        """async () => {
                          const {applyAppearance} = await import(
                            '/static/settings.js');
                          applyAppearance({theme: 'light', text_size: 'large',
                            density: 'comfortable', reduce_motion: true});
                        }"""
                    )
                    check(
                        "phone320-large-light-no-horizontal-overflow",
                        page.evaluate(
                            "()=>document.documentElement.scrollWidth<=innerWidth+1"
                        ),
                    )
                    shot(page, "phone320-large-light-long-title", True)
                    receipt["harness_completed"] = True
                except Exception as exc:
                    receipt["harness_completed"] = False
                    receipt["harness_error"] = str(exc)
                    shot(page, "failure", True)
                finally:
                    try:
                        context.close()
                        receipt["resources"]["context_closed"] = True
                    finally:
                        browser.close()
                        receipt["resources"]["browser_closed"] = True
        finally:
            server.shutdown()
            server.app.close()
            server.server_close()
            receipt["resources"]["server_closed"] = True
            thread.join(timeout=5)
            receipt["resources"]["server_thread_stopped"] = not thread.is_alive()
    receipt["source_sha256_after"] = source_hashes()
    receipt["copied_source_unchanged"] = receipt["source_sha256_after"] == source_before
    receipt["all_acceptance_checks_passed"] = (
        bool(receipt.get("harness_completed"))
        and all(c["passed"] for c in receipt["checks"])
        and not receipt["browser_errors"]
        and not receipt["external_requests"]
    )
    receipt["artifact_sha256"] = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in ART.iterdir()
        if p.is_file()
    }
    receipt["passed"] = (
        receipt["all_acceptance_checks_passed"]
        and receipt["copied_source_unchanged"]
        and all(receipt["resources"].values())
    )
    (ART / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(ART / "receipt.json")
    print(
        str(sum(row["passed"] for row in receipt["checks"]))
        + "/"
        + str(len(receipt["checks"]))
        + " checks passed."
    )
    if not receipt["passed"]:
        raise SystemExit("FAIL: inspect retained quoted-budget evidence.")
    return receipt


if __name__ == "__main__":
    main()
