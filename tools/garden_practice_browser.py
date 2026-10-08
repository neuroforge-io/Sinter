"""Run the discoverable garden project through real local storage and recovery."""

from __future__ import annotations

import hashlib
import json
import re
import sys
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))

from sinter import client, practice  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402


def main(argv: list[str] | None = None) -> None:
    started = time.perf_counter()
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    out = ROOT / "browser-artifacts"
    out.mkdir(exist_ok=True)
    receipt = out / "garden-practice-summary.json"
    receipt.write_text(json.dumps({"passed": False, "state": "running"}))
    implementation_paths = (
        "src/sinter/practice.py",
        "src/sinter/casebooks.py",
        "src/sinter/handover.py",
        "src/sinter/web/report-citations.js",
        "src/sinter/web/reports.js",
        "src/sinter/web/report-drafts.js",
        "src/sinter/web/documents.js",
        "src/sinter/web/documents.css",
        "src/sinter/web/handover-summary.js",
        "src/sinter/web/casebooks.js",
        "src/sinter/web/desktop.css",
        "src/sinter/web/library.js",
    )
    implementation = {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in implementation_paths
    }
    retained_word = None
    checks, errors, external = [], [], []
    with tempfile.TemporaryDirectory(prefix="sinter-garden-practice-") as data:
        with patch.object(
            client, "_open", side_effect=AssertionError("Offline only")
        ) as network:
            server = make_server(port=0, directory=data)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            bundle = practice.garden()
            old_book = {**bundle["casebook"], "title": "Existing local handover"}
            old_campaign = {**bundle["campaign"], "title": "Existing local campaign"}
            saved_book = server.app.casebooks.save(old_book)
            saved_campaign = server.app.campaigns.save(old_campaign)
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
                    page.goto(base + "/#home")
                    card = page.get_by_role(
                        "region", name="Fictional garden practice project"
                    )
                    for label in ("Open garden handover", "Open garden campaign"):
                        control = card.get_by_role("button", name=label, exact=True)
                        expect(control).to_be_visible()
                        bounds = control.bounding_box()
                        assert bounds and bounds["y"] + bounds["height"] < 1000
                    expect(card).to_contain_text("No account or internet needed")
                    checks.append(
                        "paired practice actions visible on the first desktop screen"
                    )
                    page.screenshot(path=str(out / "garden-practice-home.png"))
                    failed_loads = []
                    page.route(
                        "**/api/practice/garden",
                        lambda route: (
                            failed_loads.append(route.request.url),
                            route.abort(),
                        ),
                    )
                    card.get_by_role(
                        "button", name="Open garden handover", exact=True
                    ).click()
                    expect(page.get_by_role("alert")).to_contain_text(
                        "Your current project is unchanged"
                    )
                    assert len(failed_loads) == 1
                    assert server.app.casebooks.get(saved_book["id"]) == saved_book
                    assert (
                        server.app.campaigns.get(saved_campaign["id"]) == saved_campaign
                    )
                    page.unroute("**/api/practice/garden")
                    checks.append(
                        "failed example load preserves work and requires explicit retry"
                    )
                    card.get_by_role(
                        "button", name="Open garden handover", exact=True
                    ).click()
                    expect(page.get_by_label("Project name", exact=True)).to_have_value(
                        bundle["casebook"]["title"]
                    )
                    expect(page.get_by_label("Prepare a", exact=True)).to_have_value(
                        "handover"
                    )
                    sources = page.locator(".casebook-editor details.source").filter(
                        has=page.get_by_role(
                            "button",
                            name="Remove source",
                            exact=True,
                            include_hidden=True,
                        )
                    )
                    expect(sources).to_have_count(4)
                    for index, original in enumerate(bundle["casebook"]["documents"]):
                        sources.nth(index).locator("summary").click()
                        assert (
                            sources.nth(index).locator("pre").inner_text()
                            == original["content"]
                        )
                    page.get_by_label("Recipient or audience", exact=True).fill(
                        "Fictional incoming team"
                    )
                    page.get_by_role(
                        "button", name="Prepare source-only report", exact=True
                    ).click()
                    report = page.get_by_role("region", name="Your draft report")
                    expect(report).to_be_visible()
                    document = report.get_by_role(
                        "tabpanel", name="Document", exact=True
                    )
                    expect(document).to_contain_text("Source-only handover checklist")
                    expect(document).to_contain_text(
                        "The real-world answer remains unknown"
                    )
                    expect(document.get_by_role("table")).to_have_count(1)
                    expect(document.get_by_role("table")).to_contain_text(
                        "Proposed target date (unconfirmed)"
                    )
                    expect(document).not_to_contain_text(
                        "Action,Scope,Owner,Proposed target date"
                    )
                    document.get_by_role(
                        "button",
                        name=re.compile(
                            r"^Show Passage \d+: Review note - "
                            r"fictional practice conditions$"
                        ),
                    ).first.click()
                    original_note = report.locator(".source-jump[open] pre")
                    expect(original_note).to_have_text(
                        bundle["casebook"]["documents"][3]["content"]
                    )
                    checks.append(
                        "handover lays out question-specific checks and quoted "
                        "table; document citations open exact original wording"
                    )
                    report.get_by_role("tab", name="Document", exact=True).click()
                    expect(report.get_by_label("Document save state")).to_contain_text(
                        "Prepared locally; not saved"
                    )
                    assert page.evaluate("""() => {
                        const event = new Event('beforeunload', {cancelable: true});
                        window.dispatchEvent(event); return event.defaultPrevented;
                    }""")
                    report.evaluate("node => node.scrollIntoView({block: 'start'})")
                    page.screenshot(
                        path=str(out / "garden-handover-prepared-desktop.png")
                    )
                    report.get_by_text("Write handover opening", exact=True).click()
                    summary = report.locator(".handover-summary")

                    def summary_item(index, item, status, action):
                        row = summary.locator(".handover-summary-item").nth(index)
                        row.get_by_label("Item", exact=True).fill(item)
                        row.get_by_label(
                            "Recorded status or missing detail — your wording",
                            exact=True,
                        ).fill(status)
                        row.get_by_label(
                            "Next step — proposed, not accepted", exact=True
                        ).fill(action)
                        return row

                    def select_note(row, quote):
                        source = row.get_by_label(
                            "Supporting wording from this saved report", exact=True
                        )
                        choice = (
                            source.locator("option")
                            .filter(
                                has_text="Review note - fictional practice conditions"
                            )
                            .first.get_attribute("value")
                        )
                        assert choice
                        source.select_option(choice)
                        passage = row.get_by_label(
                            "Retained passage — select literal wording to use",
                            exact=True,
                        )
                        expect(passage).to_be_visible()
                        expect(passage).to_have_value(re.compile(re.escape(quote)))
                        passage.evaluate(
                            """(node, quote) => {
                            const start = node.value.indexOf(quote);
                            if (start < 0) throw new Error('Original wording missing');
                            node.focus();
                            node.setSelectionRange(start, start + quote.length);
                        }""",
                            quote,
                        )
                        row.get_by_role(
                            "button", name="Use selected wording", exact=True
                        ).click()

                    equipment = summary_item(
                        0,
                        "Equipment quote",
                        "Not received in the retained practice note.",
                        "Request the quote before proposing a purchase.",
                    )
                    select_note(equipment, "The equipment quote has not been received.")
                    equipment.locator(".handover-responsibility > summary").click()
                    equipment.get_by_label(
                        "Recorded owner type", exact=True
                    ).select_option("role")
                    equipment.get_by_label(
                        "Named person or suggested role", exact=True
                    ).fill("Fictional treasurer")
                    equipment.get_by_label(
                        "Proposed target date — unconfirmed", exact=True
                    ).fill("2026-10-09")
                    summary.get_by_role(
                        "button", name="Add summary item", exact=True
                    ).click()
                    summary_item(
                        1,
                        "Insurance excess",
                        "Unknown: no supporting record supplied.",
                        "Ask for the current insurance schedule.",
                    )
                    summary.get_by_role(
                        "button", name="Add summary item", exact=True
                    ).click()
                    guidance = summary_item(
                        2,
                        "Current funding guidance",
                        "No assigned owner in the practice note.",
                        "Nominate a volunteer to check the current funder guidance.",
                    )
                    select_note(
                        guidance, "The guideline-checking action has no assigned owner."
                    )
                    guidance.locator(".handover-responsibility > summary").click()
                    guidance.get_by_label(
                        "Recorded owner type", exact=True
                    ).select_option("unassigned")
                    summary.get_by_role(
                        "button", name="Preview opening summary", exact=True
                    ).click()
                    summary.get_by_role(
                        "button", name="Apply reviewed opening summary", exact=True
                    ).click()
                    opening = document.locator(".handover-opening-table")
                    expect(summary).not_to_have_attribute("open", "")
                    expect(opening).to_have_count(1)
                    for phrase in (
                        "Equipment quote",
                        "Insurance excess",
                        "Current funding guidance",
                        "Owner type unknown; acceptance unconfirmed",
                        "Unassigned",
                        "acceptance unconfirmed",
                        "2026-10-09 (unconfirmed; not a funder deadline)",
                        "Missing supporting record; answer remains unknown",
                    ):
                        expect(opening).to_contain_text(phrase)
                    expect(report.get_by_label("Document save state")).to_contain_text(
                        "Applied document edits have not been saved"
                    )
                    page.evaluate("document.activeElement.blur()")
                    report.evaluate("node => node.scrollIntoView({block: 'start'})")
                    first_action = (
                        opening.locator("tbody tr").first.locator("td").nth(2)
                    )
                    desktop_action = first_action.bounding_box()
                    assert desktop_action and desktop_action["y"] >= 0
                    assert desktop_action["y"] + desktop_action["height"] <= 1000
                    page.screenshot(
                        path=str(out / "garden-handover-opening-desktop.png")
                    )
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth"
                    )
                    assert opening.evaluate(
                        "node => node.scrollWidth <= node.clientWidth"
                    )
                    expect(opening.get_by_role("row")).to_have_count(4)
                    expect(opening.get_by_role("columnheader")).to_have_count(4)
                    expect(opening.get_by_role("cell")).to_have_count(12)
                    accessible = opening.aria_snapshot()
                    for phrase in (
                        "table",
                        "Item",
                        "Recorded status — user-entered",
                        "Next step — proposed",
                        "Evidence",
                        "Insurance excess",
                    ):
                        assert phrase in accessible, accessible
                    (out / "garden-handover-opening-390-aria.txt").write_text(
                        accessible
                    )
                    report.evaluate("node => node.scrollIntoView({block: 'start'})")
                    phone_action = first_action.bounding_box()
                    assert phone_action and phone_action["y"] >= 0
                    assert phone_action["y"] + phone_action["height"] <= 844
                    (out / "garden-handover-first-action-layout.json").write_text(
                        json.dumps(
                            {
                                "desktop": desktop_action,
                                "phone390": phone_action,
                                "desktop_viewport": [1440, 1000],
                                "phone_viewport": [390, 844],
                            },
                            indent=2,
                        )
                    )
                    page.screenshot(path=str(out / "garden-handover-opening-390.png"))
                    opening.evaluate("node => node.scrollIntoView({block: 'start'})")
                    page.evaluate("document.activeElement.blur()")
                    page.screenshot(path=str(out / "garden-handover-reading-390.png"))
                    (out / "garden-handover-reading-390-state.json").write_text(
                        json.dumps(
                            page.evaluate("""() => {
                            const skip = document.querySelector('.skip-link');
                            return {
                                activeElement: document.activeElement.tagName,
                                skipLinkFocused: skip.matches(':focus'),
                                skipLinkTop: getComputedStyle(skip).top,
                                horizontalOverflow:
                                    document.documentElement.scrollWidth > innerWidth
                            };
                        }"""),
                            indent=2,
                        )
                    )
                    opening.screenshot(
                        path=str(out / "garden-handover-opening-cards-390.png")
                    )
                    expect(
                        document.locator("table:not(.handover-opening-table)")
                    ).to_contain_text("Proposed target date (unconfirmed)")
                    page.set_viewport_size({"width": 1440, "height": 1000})
                    context_control = document.get_by_role(
                        "button", name="Audience and document context", exact=True
                    )
                    context_control.focus()
                    context_control.press("Space")
                    expect(context_control).to_have_attribute("aria-expanded", "true")
                    context_body = document.locator(".handover-context-content")
                    expect(context_body).to_be_visible()
                    expect(context_body).to_contain_text(
                        "Prepared for: Fictional incoming team"
                    )
                    expect(context_body).to_contain_text(
                        bundle["casebook"]["organisation"]
                    )
                    context_control.press("Space")
                    expect(context_control).to_have_attribute("aria-expanded", "false")
                    expect(context_body).to_be_hidden()
                    page.emulate_media(media="print")
                    expect(context_body).to_be_visible()
                    expect(context_body.get_by_role("heading", level=1)).to_be_visible()
                    assert (
                        context_body.bounding_box()["y"] < opening.bounding_box()["y"]
                    )
                    assert (
                        opening.evaluate("node => getComputedStyle(node).display")
                        == "table"
                    )
                    assert opening.get_by_role("columnheader").first.evaluate(
                        "node => getComputedStyle(node).backgroundColor"
                    ) == "rgb(255, 255, 255)"
                    assert opening.get_by_role("columnheader").first.evaluate(
                        "node => getComputedStyle(node).color"
                    ) == "rgb(0, 0, 0)"
                    for phrase in (
                        "Source-only handover checklist — review before using.",
                        "proposals, not accepted commitments",
                        "not independent verification",
                        "Owner type unknown; acceptance unconfirmed",
                        "Unassigned",
                        "2026-10-09 (unconfirmed; not a funder deadline)",
                    ):
                        expect(document).to_contain_text(phrase)
                    document.evaluate("node => node.scrollIntoView({block: 'start'})")
                    page.screenshot(path=str(out / "garden-handover-print-media.png"))
                    page.pdf(
                        path=str(out / "garden-handover-print.pdf"),
                        print_background=True,
                    )
                    page.emulate_media(media="screen")
                    expect(context_body).to_be_hidden()
                    expect(context_control).to_have_attribute("aria-expanded", "false")
                    checks.append(
                        "first proposal fits initial desktop and390 viewport; "
                        "keyboard context disclosure retains audience; "
                        "print includes closed context in original heading order"
                    )
                    checks.append(
                        "explicit three-row opening has actionable proposals, "
                        "exact quotations, "
                        "distinct unknown/unassigned owners and an unconfirmed date; "
                        "390px cards retain every column without changing "
                        "the original table"
                    )
                    with page.expect_download() as word_download:
                        report.get_by_role(
                            "button", name="Download Word (.docx)", exact=True
                        ).click()
                    downloaded_word = out / "offline-garden-handover.docx"
                    word_download.value.save_as(downloaded_word)
                    word_bytes = downloaded_word.read_bytes()
                    word_sha = hashlib.sha256(word_bytes).hexdigest()
                    retained_path = out / "garden-word-downloads" / (word_sha + ".docx")
                    retained_path.parent.mkdir(parents=True, exist_ok=True)
                    if retained_path.exists():
                        assert retained_path.read_bytes() == word_bytes
                    else:
                        retained_path.write_bytes(word_bytes)
                    retained_word = {
                        "path": str(retained_path.relative_to(ROOT)),
                        "sha256": word_sha,
                    }
                    with zipfile.ZipFile(downloaded_word) as archive:
                        assert archive.testzip() is None
                        word = ElementTree.fromstring(archive.read("word/document.xml"))
                    namespace = (
                        "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
                    )
                    word_text = " ".join(
                        item.text or "" for item in word.iter(namespace + "t")
                    )
                    assert word.find(".//" + namespace + "tbl") is not None
                    canonical_ids = re.findall(r"\bE[a-f0-9]{24}\b", word_text)
                    assert len(canonical_ids) == len(set(canonical_ids)) == 4
                    assert "Passage reference key" in word_text
                    for phrase in (
                        "Handover next steps",
                        "The equipment quote has not been received.",
                        "No person has accepted the actions.",
                        "not a confirmed deadline or grant closing date",
                        "The real-world answer remains unknown",
                        "Insurance excess",
                        "Missing supporting record; answer remains unknown",
                        "Request the quote before proposing a purchase.",
                    ):
                        assert phrase in word_text, phrase
                    checks.append(
                        "actual Word download contains table, negation, "
                        "unconfirmed date and unknown answer"
                    )
                    report.get_by_role("button", name="Edit draft", exact=True).click()
                    text_editor = report.get_by_label("Edit your draft", exact=True)
                    exact_reviewed = text_editor.input_value()
                    text_editor.fill(
                        exact_reviewed.replace(
                            "## At a glance",
                            "Keep this additional human warning visible.\n\n"
                            "## At a glance",
                            1,
                        )
                    )
                    report.get_by_role("button", name="Apply edits", exact=True).click()
                    expect(
                        document.get_by_text(
                            "Keep this additional human warning visible.", exact=True
                        )
                    ).to_be_visible()
                    expect(document.locator(".handover-context-content")).to_have_count(
                        0
                    )
                    report.get_by_role("button", name="Edit draft", exact=True).click()
                    text_editor.fill(exact_reviewed)
                    report.get_by_role("button", name="Apply edits", exact=True).click()
                    expect(document.locator(".handover-context-content")).to_have_count(
                        1
                    )
                    checks.append(
                        "additional human preamble stays visible; "
                        "only explicit restoration restores compact cover"
                    )
                    report.get_by_role("tab", name="Evidence", exact=True).click()
                    expect(report).to_contain_text("No wording match")
                    report.get_by_text("More options", exact=True).click()
                    report.get_by_role("button", name="Edit draft", exact=True).click()
                    pending_handover = (
                        "# Fictional edited handover\n\n"
                        "The quote is pending. No order has been approved."
                    )
                    report.get_by_label("Edit your draft", exact=True).fill(
                        pending_handover
                    )
                    checks.append(
                        "four practice sources and useful handover open "
                        "without a file picker"
                    )
                    page.get_by_role(
                        "region", name="Garden practice steps"
                    ).get_by_role("button", name="Open garden campaign").click()
                    expect(page.locator('[data-campaign-field="title"]')).to_have_value(
                        bundle["campaign"]["title"]
                    )
                    page.get_by_role("tab", name="Next actions", exact=True).click()
                    owners = page.locator('[data-campaign-field="owner"]')
                    expect(owners).to_have_count(4)
                    quote = page.get_by_role(
                        "article", name="Campaign action", exact=True
                    ).filter(has_text="Obtain equipment quote -")
                    if quote.locator("details").get_attribute("open") is None:
                        quote.locator("summary").click()
                    quote.locator('[data-campaign-field="owner"]').fill("Casey Example")
                    quote.get_by_label("Owner type", exact=True).select_option("person")
                    checks.append(
                        "paired campaign overrides latest auto-open "
                        "without overwriting it"
                    )
                    page.get_by_role(
                        "region", name="Garden practice steps"
                    ).get_by_role("button", name="Open garden handover").click()
                    expect(
                        page.get_by_label("Recipient or audience", exact=True)
                    ).to_have_value("Fictional incoming team")
                    expect(
                        report.get_by_label("Edit your draft", exact=True)
                    ).to_have_value(pending_handover)
                    report.get_by_role("button", name="Apply edits", exact=True).click()
                    expect(
                        report.get_by_role("tabpanel", name="Document", exact=True)
                    ).to_contain_text("No order has been approved.")
                    report.get_by_role(
                        "button", name="Save to My workspace", exact=True
                    ).click()
                    expect(
                        report.get_by_text(
                            "Saved in My workspace, including your edits "
                            "and original evidence.",
                            exact=True,
                        )
                    ).to_be_visible()
                    checks.append(
                        "paired return restores the same report "
                        "and unapplied handover edit"
                    )
                    page.get_by_role(
                        "region", name="Garden practice steps"
                    ).get_by_role("button", name="Open garden campaign").click()
                    expect(
                        quote.locator('[data-campaign-field="owner"]')
                    ).to_have_value("Casey Example")
                    checks.append(
                        "switching paired practice editors preserves both sets of edits"
                    )
                    page.get_by_role("button", name="Save campaign", exact=True).click()
                    expect(
                        page.get_by_text(
                            "Campaign saved. Answers, costs, checks and actions "
                            "will be here when you return.",
                            exact=True,
                        )
                    ).to_be_visible()
                    latest = next(
                        row
                        for row in server.app.campaigns.list()
                        if row["id"] != saved_campaign["id"]
                    )
                    current = server.app.campaigns.get(latest["id"])["document"]
                    assert current["actions"][1]["owner"] == "Casey Example"
                    assert current["actions"][1]["owner_confirmed"] is False
                    assert current["actions"][1]["due"] == "2026-10-09"
                    assert (
                        current["answers"][0]["text"]
                        == bundle["campaign"]["answers"][0]["text"]
                    )
                    assert (
                        current["requirements"][1]["source_url"]
                        != current["sources"][0]["url"]
                    )
                    assert (
                        server.app.campaigns.get(saved_campaign["id"]) == saved_campaign
                    )
                    assert server.app.casebooks.get(saved_book["id"]) == saved_book
                    checks.append(
                        "saving creates a fresh campaign and retains "
                        "historical and unconfirmed fields"
                    )
                    page.get_by_role(
                        "region", name="Garden practice steps"
                    ).get_by_role("button", name="Open garden handover").click()
                    page.get_by_role("button", name="Save project", exact=True).click()
                    expect(
                        page.get_by_text("Saved revision 2.", exact=False)
                    ).to_be_visible()
                    with page.expect_download() as download:
                        page.get_by_role(
                            "button", name="Export project backup", exact=True
                        ).click()
                    exported = json.loads(Path(download.value.path()).read_text())
                    assert exported["documents"] == bundle["casebook"]["documents"]
                    assert exported["recipient"] == "Fictional incoming team"
                    page.get_by_role("link", name="Overview", exact=True).click()
                    card.get_by_role(
                        "button", name="Open garden campaign", exact=True
                    ).click()
                    expect(page.locator('[data-campaign-field="title"]')).to_have_value(
                        bundle["campaign"]["title"]
                    )
                    page.close()
                    page = context.new_page()
                    page.on("pageerror", lambda error: errors.append(str(error)))
                    page.goto(base + "/#campaigns")
                    expect(page.locator('[data-campaign-field="title"]')).to_have_value(
                        bundle["campaign"]["title"]
                    )
                    page.get_by_role("tab", name="Next actions", exact=True).click()
                    reopened_quote = page.get_by_role(
                        "article", name="Campaign action", exact=True
                    ).filter(has_text="Obtain equipment quote -")
                    expect(
                        reopened_quote.locator('[data-campaign-field="owner"]')
                    ).to_have_value("Casey Example")
                    checks.append(
                        "saved practice reopens in a fresh page "
                        "and backups retain originals"
                    )
                    page.get_by_role(
                        "link", name="Community casebooks", exact=True
                    ).click()
                    page.get_by_label("Project name", exact=True).fill(
                        "Unsaved original project"
                    )
                    page.get_by_role("link", name="Overview", exact=True).click()
                    page.once("dialog", lambda dialog: dialog.dismiss())
                    page.get_by_role(
                        "button", name="Open garden handover", exact=True
                    ).click()
                    expect(
                        page.get_by_role(
                            "heading", name="Your next piece of work starts here."
                        )
                    ).to_be_visible()
                    page.get_by_role(
                        "link", name="Community casebooks", exact=True
                    ).click()
                    expect(page.get_by_label("Project name", exact=True)).to_have_value(
                        "Unsaved original project"
                    )
                    checks.append(
                        "declining replacement preserves "
                        "existing unsaved project inputs"
                    )
                    page.get_by_role("link", name="Getting started", exact=True).click()
                    expect(
                        page.get_by_role(
                            "region", name="Fictional garden practice project"
                        )
                    ).to_be_visible()
                    checks.append(
                        "getting started exposes the same complete paired project"
                    )
                    page.get_by_role("link", name="Overview", exact=True).click()
                    page.set_viewport_size({"width": 390, "height": 844})
                    assert page.evaluate(
                        "document.documentElement.scrollWidth <= innerWidth"
                    )
                    page.screenshot(
                        path=str(out / "garden-practice-narrow.png"), full_page=True
                    )
                    expect(
                        page.get_by_role(
                            "button", name="Open garden handover", exact=True
                        )
                    ).to_be_visible()
                    expect(
                        page.get_by_role(
                            "button", name="Open garden campaign", exact=True
                        )
                    ).to_be_visible()
                    checks.append(
                        "narrow view retains both practice actions "
                        "without horizontal overflow"
                    )
                    assert not errors, errors
                    assert not external, external
                    browser.close()
                network.assert_not_called()
            finally:
                server.shutdown()
                server.server_close()
                server.app.close()
    assert implementation == {
        name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
        for name in implementation_paths
    }, "Garden implementation changed during this run; rerun at a stable checkpoint."
    receipt.write_text(
        json.dumps(
            {
                "passed": True,
                "checks": checks,
                "page_errors": errors,
                "external_requests": external,
                "implementation_sha256": implementation,
                "word_download": retained_word,
                "elapsed_seconds": round(time.perf_counter() - started, 3),
            },
            indent=2,
        )
    )
    print(f"PASS: {len(checks)} real garden practice journeys; no external requests.")


if __name__ == "__main__":
    main()
