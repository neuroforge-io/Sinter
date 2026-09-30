"""Run the discoverable garden project through real local storage and recovery."""

from __future__ import annotations

import json
import sys
import tempfile
import threading
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
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    out = ROOT / "browser-artifacts"
    out.mkdir(exist_ok=True)
    receipt = out / "garden-practice-summary.json"
    receipt.write_text(json.dumps({"passed": False, "state": "running"}))
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
                    sources = page.locator(".casebook-editor details.source")
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
                        name="Show source: Review note - fictional practice conditions",
                        exact=True,
                    ).first.click()
                    original_note = report.locator(".source-jump[open] pre")
                    expect(original_note).to_have_text(
                        bundle["casebook"]["documents"][3]["content"]
                    )
                    checks.append(
                        "handover lays out question-specific checks and quoted "
                        "table; document citations open exact original wording"
                    )
                    with page.expect_download() as word_download:
                        report.get_by_role(
                            "button", name="Download Word (.docx)", exact=True
                        ).click()
                    downloaded_word = out / "offline-garden-handover.docx"
                    word_download.value.save_as(downloaded_word)
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
                    for phrase in (
                        "Handover next steps",
                        "The equipment quote has not been received.",
                        "No person has accepted the actions.",
                        "not a confirmed deadline or grant closing date",
                        "The real-world answer remains unknown",
                    ):
                        assert phrase in word_text, phrase
                    checks.append(
                        "actual Word download contains table, negation, "
                        "unconfirmed date and unknown answer"
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
                        "button", name="Save to this computer", exact=True
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
    receipt.write_text(
        json.dumps(
            {
                "passed": True,
                "checks": checks,
                "page_errors": errors,
                "external_requests": external,
            },
            indent=2,
        )
    )
    print(f"PASS: {len(checks)} real garden practice journeys; no external requests.")


if __name__ == "__main__":
    main()
