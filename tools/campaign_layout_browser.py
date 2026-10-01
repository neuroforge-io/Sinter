"""Fictional saved-campaign navigation, phone layout and focus regression proof.

Opens a temporary local campaign through the real server. Checks all section
anchors, restored offscreen tabs, unknown/owner/scope meaning, original values,
keyboard navigation, large text, reduced motion and expanded-save-error focus.
Provider calls and all non-loopback browser requests are blocked.
"""

from __future__ import annotations

import copy
import hashlib
import json
import sys
import tempfile
import threading
import traceback
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]
from sinter import client
from sinter.server import make_server
from tools._support import browser_arguments, launch_chromium
from tools.campaign_browser import CampaignChecks


def source_hashes() -> dict[str, str]:
    """Bind evidence to implementation bytes before and after this read-only run."""
    return {
        str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT / "src").rglob("*"))
        if path.is_file() and "__pycache__" not in path.parts
    }


def fictional_fixture() -> dict:
    """Use unknown application amounts and retain entered quote GST wording."""
    return {
        "schema": "sinter-campaign/v1",
        "title": "Fictional community workshop quotes and approvals",
        "organisation": "Fictional Workshop Association",
        "objective": "Record original quotes and unknown production costs; manual application "
        "amounts are not available.",
        "opportunities": [
            {
                "name": "Fictional application fund",
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
            },
            {
                "name": "Fictional second fund",
                "funder": "Fictional Fund",
                "url": "https://example.invalid/fund",
                "deadline": "",
                "decision_window": "Unknown",
                "ceiling": "200.00",
                "fit": "Fictional application basis unknown",
                "status": "researching",
                "application_mode": "required",
                "applicant": "Fictional Workshop Association",
                "applicant_confirmed": False,
                "ceiling_currency": "USD",
                "route_type": "equity",
            },
            {
                "name": "Fictional archived fund",
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
            },
        ],
        "budget": [
            {
                "item": "Fictional prototype material",
                "opportunity": "Fictional application fund",
                "quantity": 1,
                "unit_cost": "110.00",
                "quote_reference": "Fictional Quote A: AUD 110.00 including GST. Original "
                "wording retained exactly; financial_semantics "
                "unknown.",
            },
            {
                "item": "Fictional finishing work",
                "opportunity": "Fictional application fund",
                "quantity": 1,
                "unit_cost": "100.00",
                "quote_reference": "Fictional Quote B: AUD 100.00 excluding GST. Original "
                "wording retained exactly; financial_semantics "
                "unknown.",
            },
            {
                "item": "Fictional production cost unknown",
                "opportunity": "Fictional application fund",
                "quantity": 1,
                "unit_cost": None,
                "quote_reference": "",
            },
            {
                "item": "Fictional historical cost",
                "opportunity": "Fictional archived fund",
                "quantity": 1,
                "unit_cost": "10.00",
                "quote_reference": "Fictional old quote; retained as historical evidence "
                "only",
            },
        ],
        "answers": [
            {
                "opportunity": "Fictional application fund",
                "label": "Fictional project purpose",
                "text": "Fictional answer needs human shortening. Fictional answer needs "
                "human shortening. Fictional answer needs human shortening. "
                "Fictional answer needs human shortening. Fictional answer needs "
                "human shortening. ",
                "limit": 30,
                "status": "reviewed",
            },
            {
                "opportunity": "Fictional second fund",
                "label": "Second current answer",
                "text": "Fictional second application answer",
                "limit": 300,
                "status": "reviewed",
            },
            {
                "opportunity": "Fictional archived fund",
                "label": "Archived answer",
                "text": "Fictional historical answer; old review is preserved as "
                "historical only",
                "limit": 300,
                "status": "reviewed",
            },
        ],
        "requirements": [
            {
                "opportunity": "Fictional application fund",
                "rule": "Confirm whether this applicant and production cost are "
                "permitted",
                "status": "unknown",
                "evidence": "Fictional eligibility evidence not received.",
            },
            {
                "opportunity": "Fictional application fund",
                "rule": "Check the stated current round and required project dates",
                "status": "met",
                "evidence": "",
            },
        ],
        "actions": [
            {
                "opportunity": "Fictional application fund",
                "scope_confirmed": True,
                "task": "Ask the fictional provider for an itemised production quote and "
                "retain the original GST wording.",
                "owner": "Fictional coordinator",
                "owner_kind": "person",
                "owner_confirmed": False,
                "due": "2026-10-20",
                "status": "open",
            },
            {
                "opportunity": "",
                "scope_confirmed": False,
                "task": "Fictional old action: confirm whether it belongs to this "
                "campaign before treating it as current.",
                "owner": "",
                "status": "open",
            },
            {
                "opportunity": "Fictional archived fund",
                "scope_confirmed": True,
                "task": "Fictional historical action: reconsider current scope rather "
                "than silently treating it as work.",
                "owner": "",
                "status": "open",
            },
            {
                "opportunity": "Fictional application fund",
                "scope_confirmed": True,
                "task": "Fictional held action retained by explicit choice; not "
                "completed.",
                "owner": "",
                "status": "held",
            },
        ],
        "sources": [],
    }


def main(argv: Sequence[str] | None = None) -> dict:
    """Handle optional browser setup before opening any resource or artifact."""
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifact_root = ROOT / "browser-artifacts"
    artifact_root.mkdir(exist_ok=True)
    ART = Path(tempfile.mkdtemp(prefix="campaign-layout-", dir=artifact_root))
    fixture = fictional_fixture()
    route = fixture["opportunities"][0]["name"]
    (ART / "input-original.json").write_text(json.dumps(fixture, indent=2) + "\n")
    receipt = {
        "source": str(ROOT),
        "scope": "Fictional saved-campaign layout journey, no provider or external browser calls",
        "checks": [],
        "geometry": {},
        "screenshots": [],
        "errors": [],
        "external": [],
        "resources": {},
    }
    receipt["source_before"] = source_hashes()
    receipt["producer_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()

    def check(n, v, d=None):
        receipt["checks"].append({"check": n, "passed": bool(v), "detail": d})

    def geometry(page, name):
        value = page.evaluate(
            """()=>{const result={scroll:scrollY,viewport:{width:innerWidth,height:innerHeight},pageHeight:document.documentElement.scrollHeight};for(const [key,selector]of Object.entries({save:'.campaign-save-bar',tabs:'.campaign-tabs',decision:'.campaign-decision-card',saved:'.campaign-saved-panel',summary:'.campaign-summary',panel:'.campaign-section',firstCost:'.campaign-budget-row',firstAction:'.campaign-action',output:'#campaign-output',report:'.report-heading'})){const el=document.querySelector(selector);if(el){const r=el.getBoundingClientRect();result[key]={top:r.top,bottom:r.bottom,height:r.height,pageTop:r.top+scrollY,width:r.width}}}return result}"""
        )
        receipt["geometry"][name] = value
        return value

    def visible_clear(locator):
        return locator.evaluate(
            """el=>{const r=el.getBoundingClientRect();const x=r.left+r.width/2,y=r.top+Math.min(r.height/2,22);const top=document.elementFromPoint(x,y);return r.top>=0&&r.bottom<=innerHeight&&top&&(el.contains(top)||top.contains(el))}"""
        )

    def shot(page, name, full=False):
        page.screenshot(
            path=str(ART / (name + ".png")), full_page=full, animations="disabled"
        )
        receipt["screenshots"].append(name + ".png")

    with (
        tempfile.TemporaryDirectory(prefix="sinter-phone-fictional-") as data,
        ExitStack() as guard,
    ):
        for n in ["chat", "search", "_post", "_get", "_open"]:
            guard.enter_context(
                patch.object(
                    client, n, side_effect=AssertionError("Unexpected provider call")
                )
            )
        server = make_server(port=0, directory=data)
        saved = server.app.campaigns.save(copy.deepcopy(fixture))
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            with sync_playwright() as pw:
                browser = launch_chromium(pw, args.chromium)
                base = f"http://127.0.0.1:{server.server_port}"
                context = browser.new_context(
                    viewport={"width": 390, "height": 844},
                    accept_downloads=True,
                    reduced_motion="reduce",
                )

                def network(route):
                    if route.request.url.startswith(base + "/"):
                        route.continue_()
                    else:
                        receipt["external"].append(route.request.url)
                        route.abort()

                context.route("**/*", network)
                page = context.new_page()
                page.set_default_timeout(10000)
                page.on("dialog", lambda d: d.accept())
                page.on("pageerror", lambda e: receipt["errors"].append(str(e)))
                checks = CampaignChecks(browser, base, ART)

                def backup(name):
                    checks.transfers(page)
                    with page.expect_download() as down:
                        page.get_by_role(
                            "button", name="Export campaign backup", exact=True
                        ).click()
                    path = ART / (name + ".json")
                    down.value.save_as(str(path))
                    return json.loads(path.read_text())

                try:
                    for width, height in [(390, 844), (790, 884), (1440, 1000)]:
                        prefix = str(width)
                        page.set_viewport_size({"width": width, "height": height})
                        checks.goto(page, "campaigns")
                        expect(
                            page.get_by_label("Campaign name", exact=True)
                        ).to_have_value(fixture["title"])
                        page.evaluate("()=>window.scrollTo(0,0)")
                        initial = backup(prefix + "-initial")
                        page.evaluate("()=>window.scrollTo(0,0)")
                        receipt["geometry"][prefix + "-opening"] = geometry(
                            page, prefix + "-opening"
                        )
                        shot(page, prefix + "-opening")
                        shot(page, prefix + "-opening-full", True)
                        opening = receipt["geometry"][prefix + "-opening"]
                        check(
                            prefix + "-section-navigation-in-first-viewport",
                            opening["tabs"]["bottom"] <= height
                            and opening["tabs"]["top"] >= 0,
                            opening["tabs"],
                        )
                        check(
                            prefix + "-section-navigation-one-row",
                            page.locator(".campaign-tabs .campaign-tab").evaluate_all(
                                "(els)=>Math.max(...els.map(el=>el.getBoundingClientRect().top))-Math.min(...els.map(el=>el.getBoundingClientRect().top))<1"
                            ),
                        )
                        check(
                            prefix + "-section-tabs-44px-targets",
                            page.locator(".campaign-tabs .campaign-tab").evaluate_all(
                                "(els)=>els.every(el=>el.getBoundingClientRect().height>=44)"
                            ),
                        )
                        check(
                            prefix + "-all-nine-readiness-meanings-retained",
                            page.locator(".campaign-summary>div").count() == 9
                            and page.locator(
                                ".campaign-summary span"
                            ).all_text_contents()
                            == [
                                "requirements to check",
                                "answers to shorten",
                                "answer rows held",
                                "costs needing a quote",
                                "application windows to verify",
                                "funding currencies to review",
                                "owners to confirm",
                                "actions to review",
                                "actions on hold",
                            ],
                        )
                        decision = page.get_by_role(
                            "region", name="Campaign decision and next move"
                        )
                        check(
                            prefix + "-decision-unknown-and-owner-meaning-retained",
                            "NOT READY" in decision.inner_text()
                            and "Reopen or progress when" in decision.inner_text()
                            and "Sinter" in decision.inner_text(),
                        )
                        for section in [
                            "Opportunities",
                            "Products & IP",
                            "Application answers",
                            "Budget",
                            "Next actions",
                            "Communications",
                            "Sources",
                        ]:
                            page.get_by_role("tab", name=section, exact=True).click()
                            panel = page.locator(".campaign-section")
                            expect(panel).to_be_focused()
                            section_geometry = geometry(
                                page, prefix + "-section-" + section
                            )
                            heading = panel.locator("h3").first
                            check(
                                prefix
                                + "-"
                                + section
                                + "-explicit-panel-and-heading-clear",
                                panel.get_attribute("aria-label") == section
                                and section_geometry["panel"]["top"]
                                >= section_geometry["tabs"]["bottom"] + 10
                                and heading.bounding_box()["y"]
                                >= section_geometry["tabs"]["bottom"] + 10,
                                section_geometry,
                            )
                        page.get_by_role("tab", name="Budget", exact=True).click()
                        geometry(page, prefix + "-budget-selected")
                        shot(page, prefix + "-budget-selected")
                        chosen = receipt["geometry"][prefix + "-budget-selected"]
                        check(
                            prefix + "-selected-panel-clears-sticky-controls",
                            chosen["panel"]["top"] >= chosen["tabs"]["bottom"] + 10
                            and chosen["panel"]["top"] <= chosen["tabs"]["bottom"] + 22,
                            chosen,
                        )
                        check(
                            prefix + "-section-click-focuses-live-named-panel",
                            page.locator(".campaign-section").evaluate(
                                'el=>el===document.activeElement&&el.isConnected&&el.getAttribute("aria-label")=="Budget"'
                            ),
                        )
                        check(
                            prefix + "-selected-route-and-all-cost-scopes-visible",
                            route
                            in page.locator(".campaign-section-context").inner_text()
                            and "All current campaign costs"
                            in page.locator(".campaign-section-context").inner_text(),
                        )
                        check(
                            prefix + "-next-cost-control-clear-after-section-selection",
                            visible_clear(
                                page.get_by_role(
                                    "button",
                                    name="Open the next cost to check",
                                    exact=True,
                                )
                            ),
                        )
                        check(
                            prefix + "-basis-note-precedes-cost-control",
                            page.locator(".campaign-budget-basis-note").evaluate(
                                'el=>Boolean(el.compareDocumentPosition([...document.querySelectorAll("button")].find(b=>b.textContent==="Open the next cost to check"))&Node.DOCUMENT_POSITION_FOLLOWING)'
                            ),
                        )
                        check(
                            prefix + "-budget-basis-and-unknown-retained",
                            "No GST conversion was made"
                            in page.locator(".campaign-budget-basis-note").inner_text()
                            and "total incomplete"
                            in page.locator(".campaign-budget-total").inner_text(),
                        )
                        page.get_by_role(
                            "button", name="Open the next cost to check", exact=True
                        ).click()
                        focus = page.locator(
                            '[data-budget-index="2"] [data-campaign-field="unit_cost"]'
                        )
                        expect(focus).to_be_focused()
                        geometry(page, prefix + "-budget-focused")
                        shot(page, prefix + "-budget-focused")
                        check(
                            prefix + "-missing-price-focus-clear", visible_clear(focus)
                        )
                        page.get_by_role("tab", name="Next actions", exact=True).click()
                        geometry(page, prefix + "-actions-selected")
                        shot(page, prefix + "-actions-selected")
                        page.get_by_role(
                            "button", name="Campaign status", exact=True
                        ).click()
                        status_geometry = geometry(page, prefix + "-status-anchor")
                        check(
                            prefix + "-status-anchor-clears-sticky-controls",
                            status_geometry["decision"]["top"]
                            >= status_geometry["tabs"]["bottom"] + 10,
                        )
                        page.get_by_role(
                            "button", name="Open full action", exact=True
                        ).click()
                        task = page.locator(
                            '[data-action-index="0"] [data-campaign-field="task"]'
                        )
                        expect(task).to_be_focused()
                        geometry(page, prefix + "-action-anchor")
                        shot(page, prefix + "-action-anchor")
                        check(prefix + "-deep-action-focus-clear", visible_clear(task))
                        page.get_by_role("tab", name="Next actions", exact=True).focus()
                        page.keyboard.press("ArrowRight")
                        check(
                            prefix + "-arrow-navigation-live-selected-focus",
                            page.evaluate(
                                '()=>document.activeElement.getAttribute("role")=="tab"&&document.activeElement.getAttribute("aria-selected")=="true"&&document.activeElement.isConnected'
                            ),
                        )
                        check(
                            prefix + "-arrow-selected-tab-not-covered",
                            visible_clear(
                                page.get_by_role(
                                    "tab", name="Communications", exact=True
                                )
                            ),
                        )
                        page.keyboard.press("ArrowLeft")
                        page.get_by_role("tab", name="Next actions", exact=True).press(
                            "Enter"
                        )
                        check(
                            prefix + "-keyboard-enter-opens-and-focuses-action-panel",
                            page.locator(".campaign-section").evaluate(
                                'el=>el===document.activeElement&&el.getAttribute("aria-label")=="Next actions"'
                            ),
                        )
                        check(
                            prefix + "-scope-owner-hold-meaning-retained",
                            "acceptance unconfirmed"
                            in page.locator(".campaign-section").inner_text()
                            and "Scope needs confirmation"
                            in page.locator(".campaign-section").inner_text()
                            and "On hold"
                            in page.locator(".campaign-section").inner_text(),
                        )
                        page.get_by_role(
                            "button", name="Prepare campaign brief", exact=True
                        ).click()
                        expect(
                            page.get_by_role("region", name="Your draft report")
                        ).to_be_visible()
                        geometry(page, prefix + "-brief-prepared")
                        shot(page, prefix + "-brief-prepared")
                        shot(page, prefix + "-brief-full", True)
                        prepared = receipt["geometry"][prefix + "-brief-prepared"]
                        check(
                            prefix + "-report-heading-clears-sticky-controls",
                            prepared["report"]["top"]
                            >= prepared["tabs"]["bottom"] + 10,
                            prepared,
                        )
                        check(
                            prefix + "-brief-basis-meaning-retained",
                            "not an eligibility or application-ceiling decision"
                            in page.get_by_role(
                                "region", name="Your draft report"
                            ).inner_text(),
                        )
                        check(
                            prefix + "-layout-only-exact-originals-and-reviews",
                            backup(prefix + "-final") == initial,
                        )
                        check(
                            prefix + "-no-horizontal-page-overflow",
                            page.evaluate(
                                "()=>document.documentElement.scrollWidth<=innerWidth+1"
                            ),
                        )
                        check(
                            prefix + "-saved-revision-unchanged",
                            server.app.campaigns.get(saved["id"]) == saved,
                        )
                    page.set_viewport_size({"width": 390, "height": 844})
                    for section in ["Products & IP", "Communications", "Sources"]:
                        page.get_by_role("tab", name=section, exact=True).click()
                        page.get_by_role(
                            "link", name="Sinter overview", exact=True
                        ).click()
                        expect(page.locator("#page-title")).to_have_text("Overview")
                        page.get_by_role(
                            "button", name="Find a tool", exact=False
                        ).click()
                        page.get_by_label("Find a Sinter tool", exact=True).fill(
                            "Funding campaigns"
                        )
                        page.get_by_label("Find a Sinter tool", exact=True).press(
                            "Enter"
                        )
                        expect(page.locator(".campaign-save-bar")).to_be_visible()
                        page.evaluate(
                            "()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve)))"
                        )
                        restored = page.locator(
                            ".campaign-section-navigation"
                        ).evaluate(
                            'el=>{const tabs=el.querySelector("[role=tablist]"),chosen=el.querySelector("[aria-selected=true]"),a=tabs.getBoundingClientRect(),b=chosen.getBoundingClientRect();return {left:a.left,right:a.right,chosenLeft:b.left,chosenRight:b.right,text:chosen.textContent,scroll:scrollY}}'
                        )
                        check(
                            "390-restored-" + section + "-selected-tab-visible",
                            restored["text"] == section
                            and restored["chosenLeft"] >= restored["left"] - 1
                            and restored["chosenRight"] <= restored["right"] + 1,
                            restored,
                        )
                        check(
                            "390-restored-"
                            + section
                            + "-attachment-does-not-scroll-page",
                            restored["scroll"] == 0,
                            restored,
                        )
                        shot(page, "390-restored-" + section.replace(" ", "-"))
                    # A fresh small viewport catches focus below the action article.
                    for width, height in [(320, 568), (390, 440)]:
                        key = f"{width}-{height}-24px-action"
                        short_context = browser.new_context(
                            viewport={"width": width, "height": height},
                            reduced_motion="reduce",
                        )
                        try:
                            short_context.route("**/*", network)
                            short_page = short_context.new_page()
                            short_page.on(
                                "pageerror",
                                lambda error: receipt["errors"].append(str(error)),
                            )
                            short_page.goto(base + "/#campaigns")
                            expect(
                                short_page.get_by_label("Campaign name", exact=True)
                            ).to_have_value(fixture["title"])
                            short_page.evaluate(
                                '()=>document.documentElement.style.fontSize="24px"'
                            )
                            short_page.get_by_role(
                                "tab", name="Next actions", exact=True
                            ).click()
                            short_page.get_by_role(
                                "button", name="Campaign status", exact=True
                            ).click()
                            short_page.get_by_role(
                                "button", name="Open full action", exact=True
                            ).click()
                            task = short_page.locator(
                                '[data-action-index="0"] [data-campaign-field="task"]'
                            )
                            expect(task).to_be_focused()
                            state = geometry(short_page, key)
                            rect = task.bounding_box()
                            shot(short_page, key)
                            check(
                                key + "-full-task-visible",
                                rect["y"] >= state["tabs"]["bottom"] + 4
                                and rect["y"] + rect["height"] <= height,
                                {"task": rect, "controls": state["tabs"]},
                            )
                            check(
                                key + "-saved-originals-exact",
                                server.app.campaigns.get(saved["id"]) == saved,
                            )
                        finally:
                            short_context.close()
                            receipt["resources"][key + "-context_closed"] = True
                    page.set_viewport_size({"width": 320, "height": 844})
                    page.evaluate(
                        """async()=>{const {applyAppearance}=await import('/static/settings.js');applyAppearance({theme:'light',text_size:'large',density:'comfortable',reduce_motion:true})}"""
                    )
                    page.get_by_role("tab", name="Budget", exact=True).click()
                    geometry(page, "320-large-budget")
                    shot(page, "320-large-budget")
                    check(
                        "320-large-no-horizontal-overflow",
                        page.evaluate(
                            "()=>document.documentElement.scrollWidth<=innerWidth+1"
                        ),
                    )
                    check(
                        "320-large-reduced-motion-is-respected",
                        page.evaluate(
                            '()=>matchMedia("(prefers-reduced-motion: reduce)").matches&&getComputedStyle(document.documentElement).scrollBehavior!=="smooth"'
                        ),
                    )
                    page.get_by_role(
                        "button", name="Open the next cost to check", exact=True
                    ).click()
                    largefocus = page.locator(
                        '[data-budget-index="2"] [data-campaign-field="unit_cost"]'
                    )
                    expect(largefocus).to_be_focused()
                    geometry(page, "320-large-price-focus")
                    shot(page, "320-large-price-focus")
                    check(
                        "320-large-price-focus-not-covered", visible_clear(largefocus)
                    )
                    page.get_by_role(
                        "button", name="Prepare campaign brief", exact=True
                    ).click()
                    expect(
                        page.get_by_role("region", name="Your draft report")
                    ).to_be_visible()
                    large = geometry(page, "320-large-brief")
                    shot(page, "320-large-brief")
                    check(
                        "320-large-report-heading-clears-controls",
                        large["report"]["top"] >= large["tabs"]["bottom"] + 10,
                    )
                    page.set_viewport_size({"width": 390, "height": 580})
                    page.get_by_role("tab", name="Budget", exact=True).click()
                    page.get_by_role(
                        "button", name="Open the next cost to check", exact=True
                    ).click()
                    expect(largefocus).to_be_focused()
                    geometry(page, "390-short-large-price")
                    shot(page, "390-short-large-price")
                    check(
                        "390-short-large-price-not-covered", visible_clear(largefocus)
                    )
                    page.set_viewport_size({"width": 390, "height": 844})
                    page.get_by_role("tab", name="Budget", exact=True).click()
                    row0 = page.locator('[data-budget-index="0"]')
                    if not row0.locator("details").evaluate("el=>el.open"):
                        row0.locator("summary").click()
                    row0.get_by_label("Quote or estimate reference", exact=True).fill(
                        fixture["budget"][0]["quote_reference"]
                        + " Fictional unsaved clarification."
                    )

                    def reject_save(route):
                        route.fulfill(
                            status=409,
                            content_type="application/json",
                            body=json.dumps(
                                {
                                    "error": "Fictional stale revision. "
                                    + "Current edits remain available for a local backup. "
                                    * 15
                                }
                            ),
                        )

                    page.route("**/api/campaigns/save", reject_save)
                    page.get_by_role("button", name="Save campaign", exact=True).click()
                    expect(page.get_by_role("alert")).to_contain_text(
                        "Fictional stale revision"
                    )
                    page.get_by_role(
                        "button", name="Open the next cost to check", exact=True
                    ).click()
                    expect(largefocus).to_be_focused()
                    fault = geometry(page, "390-large-save-error-price")
                    rect = largefocus.evaluate(
                        "el=>({top:el.getBoundingClientRect().top,bottom:el.getBoundingClientRect().bottom})"
                    )
                    fault["focused"] = rect
                    shot(page, "390-large-save-error-price")
                    check(
                        "390-large-save-error-full-price-field-clears-controls",
                        rect["top"] >= fault["tabs"]["bottom"] + 4
                        and rect["bottom"] <= 844,
                        {"focus": rect, "tabs": fault["tabs"], "save": fault["save"]},
                    )
                    check(
                        "rejected-save-layout-preserves-original-saved-record",
                        server.app.campaigns.get(saved["id"]) == saved,
                    )
                    page.unroute("**/api/campaigns/save", reject_save)
                    receipt["completed"] = True
                except Exception:
                    receipt["completed"] = False
                    receipt["error"] = traceback.format_exc()
                    shot(page, "failure", True)
                finally:
                    context.close()
                    receipt["resources"]["context_closed"] = True
                    browser.close()
                    receipt["resources"]["browser_closed"] = True
        finally:
            server.shutdown()
            server.app.close()
            server.server_close()
            thread.join(timeout=5)
            receipt["resources"]["server_closed"] = True
            receipt["resources"]["server_thread_stopped"] = not thread.is_alive()
    receipt["source_after"] = source_hashes()
    receipt["source_unchanged"] = receipt["source_before"] == receipt["source_after"]
    receipt["failed"] = [c for c in receipt["checks"] if not c["passed"]]
    receipt["passed"] = (
        bool(receipt.get("completed"))
        and not receipt["failed"]
        and not receipt["errors"]
        and not receipt["external"]
        and receipt["source_unchanged"]
        and all(receipt["resources"].values())
    )
    (ART / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(ART / "receipt.json")
    print(
        sum(c["passed"] for c in receipt["checks"]),
        "/",
        len(receipt["checks"]),
        receipt.get("error", ""),
    )

    if not receipt["passed"]:
        raise SystemExit("FAIL: inspect retained campaign layout evidence.")
    return receipt


if __name__ == "__main__":
    main()
