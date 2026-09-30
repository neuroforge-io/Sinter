"""Fictional offline handover selection, Word export and backup browser proof."""

from __future__ import annotations

import hashlib
import json
import sys
import tempfile
import threading
import zipfile
from pathlib import Path
from unittest.mock import patch
from xml.etree import ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from sinter import casebooks, client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402

W = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
FIXTURE = ROOT / "tests/fixtures/handover-appendix.json"


def word_text(path: Path) -> str:
    """Extract text and line breaks from the actual downloaded Word package."""
    with zipfile.ZipFile(path) as archive:
        tree = ET.fromstring(archive.read("word/document.xml"))
    return "\n".join(
        "".join(
            (node.text or "") if node.tag == f"{{{W}}}t" else "\n"
            for node in paragraph.iter()
            if node.tag in {f"{{{W}}}t", f"{{{W}}}br"}
        )
        for paragraph in tree.findall(f".//{{{W}}}p")
    )


def main(argv: list[str] | None = None) -> None:
    """Use the real interface in a disposable fictional local workspace."""
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-handover-appendix-proof-"))
    original = json.loads(FIXTURE.read_text(encoding="utf-8"))
    original_copy = json.loads(json.dumps(original))
    compact = casebooks.build(original)
    selected = casebooks.build({**original, "handover_evidence": "selected_appendix"})
    checks, errors, external = [], [], []
    resources = {"browser_closed": False, "server_closed": False}
    source_paths = (
        "src/sinter/handover.py",
        "src/sinter/casebooks.py",
        "src/sinter/web/casebooks.js",
        "src/sinter/web/desktop.css",
        "src/sinter/web/casebook-handover.js",
        "src/sinter/docx_export.py",
        "tests/fixtures/handover-appendix.json",
        "tools/handover_appendix_browser.py",
    )
    receipt = {
        "passed": False,
        "source_sha256": {
            name: hashlib.sha256((ROOT / name).read_bytes()).hexdigest()
            for name in source_paths
        },
        "scope": "Fictional source-app browser proof; no installed qualification",
    }

    def download_word(page, report, filename):
        with page.expect_download() as received:
            report.get_by_role("button", name="Download Word (.docx)").click()
        path = artifacts / filename
        received.value.save_as(path)
        return path

    def check_selected_word(path):
        text = word_text(path)
        assert "Including all 9 selected passages from 7 sources" in text
        assert "Selected evidence appendix" in text
        for excerpt in selected["excerpts"]:
            assert excerpt["quote"] in text
            assert text.count(excerpt["id"]) == 1
        assert "UNSELECTED ORIGINAL CONTEXT" not in text
        assert "Evidence only — not reproduced" not in text
        assert "not an exhaustive source review" in text
        assert "09:45 on 7 October; it is proposed, not confirmed" in text
        assert "current fictional scope is one small pilot" in text
        assert "IP ownership and novelty remain unverified" in text
        assert "No named person has accepted the fictional follow-up" in text
        assert "李 😀" in text

    with tempfile.TemporaryDirectory(prefix="sinter-handover-workspace-") as data:
        with patch.object(
            client, "_open", side_effect=AssertionError("Offline source-only proof")
        ) as remote:
            server = make_server(port=0, directory=data)
            saved = server.app.casebooks.save(original)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with sync_playwright() as driver:
                    browser = launch_chromium(driver, args.chromium)
                    try:
                        context = browser.new_context(
                            viewport={"width": 1440, "height": 1000},
                            accept_downloads=True,
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
                        page.set_default_timeout(10000)
                        page.on("pageerror", lambda error: errors.append(str(error)))
                        page.on("dialog", lambda dialog: dialog.accept())
                        page.goto(base + "/#casebooks")
                        page.get_by_role("button", name="Open project").click()
                        mode = page.get_by_label(
                            "Evidence in source-only handover", exact=True
                        )
                        expect(mode).to_have_value("compact")
                        page.get_by_role(
                            "button", name="Prepare source-only report", exact=True
                        ).click()
                        report = page.get_by_role("region", name="Your draft report")
                        expect(report).to_be_visible()
                        document = report.get_by_role("tabpanel", name="Document")
                        expect(document).to_contain_text("Showing 4 of 9")
                        expect(document).not_to_contain_text(
                            "Selected evidence appendix"
                        )
                        compact_word = download_word(page, report, "compact.docx")
                        assert (
                            word_text(compact_word).count(
                                "Evidence only — not reproduced"
                            )
                            == 5
                        )
                        report.get_by_role(
                            "button", name="Save to this computer", exact=True
                        ).click()
                        expect(report).to_contain_text("Saved in My workspace")
                        historical_id = server.app.store.reports()[0]["id"]
                        historical = server.app.store.report(historical_id)
                        checks.append(
                            "Existing compact default and saved report retained."
                        )

                        mode.select_option("selected_appendix")
                        expect(report).to_have_count(0)
                        page.get_by_role("link", name="Recent activity").click()
                        page.get_by_role("link", name="Community casebooks").click()
                        expect(
                            page.get_by_label(
                                "Evidence in source-only handover", exact=True
                            )
                        ).to_have_value("selected_appendix")
                        checks.append(
                            "Explicit mode invalidates the old preparation and "
                            "survives navigation as an unsaved choice."
                        )
                        page.get_by_role(
                            "button", name="Prepare source-only report", exact=True
                        ).click()
                        report = page.get_by_role("region", name="Your draft report")
                        expect(report).to_be_visible()
                        expect(
                            page.get_by_text(
                                "This prepared handover includes "
                                "all 9 selected passages.",
                                exact=False,
                            )
                        ).to_be_visible()
                        appendix_word = download_word(page, report, "selected.docx")
                        check_selected_word(appendix_word)
                        current = server.app.casebooks.get(saved["id"])
                        assert current["document"]["handover_evidence"] == (
                            "selected_appendix"
                        )
                        assert (
                            current["document"]["documents"]
                            == (saved["document"]["documents"])
                        )
                        assert (
                            current["document"]["fingerprint"]
                            != (compact["casebook_fingerprint"])
                        )
                        assert server.app.store.report(historical_id) == historical
                        checks.append(
                            "Actual Word carries all nine exact selected excerpts, "
                            "supplied links/dates and late uncertain facts; "
                            "unselected original text stays out."
                        )
                        page.screenshot(path=str(artifacts / "selected-handover.png"))

                        with page.expect_download() as received:
                            page.get_by_role(
                                "button", name="Export project backup", exact=True
                            ).click()
                        backup_path = artifacts / "selected-project.json"
                        received.value.save_as(backup_path)
                        backup = json.loads(backup_path.read_text())
                        assert backup["handover_evidence"] == "selected_appendix"
                        assert backup["documents"] == current["document"]["documents"]
                        assert (
                            "UNSELECTED ORIGINAL CONTEXT"
                            in (backup["documents"][0]["content"])
                        )
                        page.close()
                        server.shutdown()
                        server.app.close()
                        server.server_close()
                        thread.join(timeout=5)
                        assert not thread.is_alive()
                        # Start a fresh application against the same fictional
                        # workspace, not the previous page or app's memory.
                        server = make_server(port=0, directory=data)
                        thread = threading.Thread(
                            target=server.serve_forever, daemon=True
                        )
                        thread.start()
                        base = f"http://127.0.0.1:{server.server_port}"
                        assert server.app.store.report(historical_id) == historical
                        reopened = context.new_page()
                        reopened.on(
                            "pageerror", lambda error: errors.append(str(error))
                        )
                        reopened.on("dialog", lambda dialog: dialog.accept())
                        reopened.goto(base + "/#casebooks")
                        reopened.get_by_role("button", name="Open project").click()
                        expect(
                            reopened.get_by_label(
                                "Evidence in source-only handover", exact=True
                            )
                        ).to_have_value("selected_appendix")
                        reopened.get_by_role(
                            "button", name="Prepare source-only report", exact=True
                        ).click()
                        reopened_report = reopened.get_by_role(
                            "region", name="Your draft report"
                        )
                        expect(reopened_report).to_be_visible()
                        check_selected_word(
                            download_word(
                                reopened, reopened_report, "reopened-selected.docx"
                            )
                        )
                        checks.append(
                            "Closing and restarting the local application uses "
                            "the saved mode and regenerates the complete selected Word."
                        )

                        reopened.get_by_label("Prepare a", exact=True).select_option(
                            "brief"
                        )
                        expect(
                            reopened.get_by_label(
                                "Evidence in source-only handover", exact=True
                            )
                        ).to_be_hidden()
                        reopened.get_by_label("Prepare a", exact=True).select_option(
                            "handover"
                        )
                        expect(
                            reopened.get_by_label(
                                "Evidence in source-only handover", exact=True
                            )
                        ).to_have_value("selected_appendix")
                        before_restore = server.app.casebooks.get(saved["id"])
                        reopened.get_by_text(
                            "Backups and project removal", exact=True
                        ).click()
                        reopened.get_by_label(
                            "Restore a casebook backup", exact=True
                        ).set_input_files(backup_path)
                        expect(
                            reopened.get_by_text(
                                "Backup opened as a new unsaved project.", exact=True
                            )
                        ).to_be_visible()
                        expect(
                            reopened.get_by_label(
                                "Evidence in source-only handover", exact=True
                            )
                        ).to_have_value("selected_appendix")
                        reopened.get_by_label("Project name", exact=True).fill(
                            "Restored fictional selected-evidence handover"
                        )
                        reopened.get_by_role(
                            "button", name="Save project", exact=True
                        ).click()
                        expect(
                            reopened.get_by_role(
                                "button", name="Open project", exact=True
                            )
                        ).to_have_count(2)
                        assert server.app.casebooks.get(saved["id"]) == before_restore
                        assert server.app.store.report(historical_id) == historical
                        checks.append(
                            "Format changes retain the explicit choice; backup "
                            "restores to a separate record without rewriting "
                            "originals or the historical report."
                        )
                        reopened.get_by_role(
                            "button", name="Prepare source-only report", exact=True
                        ).click()
                        expect(
                            reopened.get_by_role("region", name="Your draft report")
                        ).to_be_visible()
                        reopened.get_by_label(
                            "Evidence in source-only handover", exact=True
                        ).select_option("compact")
                        expect(
                            reopened.get_by_role("region", name="Your draft report")
                        ).to_have_count(0)
                        reopened.get_by_role(
                            "button", name="Prepare source-only report", exact=True
                        ).click()
                        expect(
                            reopened.get_by_role(
                                "tabpanel", name="Document", exact=True
                            )
                        ).to_contain_text("Showing 4 of 9")
                        assert server.app.store.report(historical_id) == historical
                        checks.append(
                            "Returning to compact requires a new preparation; "
                            "historical exports are unchanged."
                        )
                        layout = """() => ({
                            viewport: innerWidth,
                            width: document.documentElement.scrollWidth,
                            overflowing: [...document.querySelectorAll(
                              'input,select,fieldset,details')]
                              .filter(node => node.getBoundingClientRect().right
                                > innerWidth + 1)
                              .map(node => ({tag:node.tagName,type:node.type || '',
                                label:node.closest('label')?.textContent || '',
                                right:node.getBoundingClientRect().right,
                                width:node.getBoundingClientRect().width}))
                        })"""
                        receipt["narrow_layout"] = []
                        for width in (390, 1440, 390, 320, 1440, 390):
                            reopened.set_viewport_size({"width": width, "height": 844})
                            # Reflow cached source details as the viewport changes.
                            # A stale implicit grid track must never widen controls.
                            reopened.get_by_label(
                                "Evidence in source-only handover", exact=True
                            ).scroll_into_view_if_needed()
                            reopened.screenshot(
                                path=str(artifacts / f"width-{width}.png")
                            )
                            measurement = reopened.evaluate(layout)
                            receipt["narrow_layout"].append(measurement)
                            assert measurement["width"] <= width + 1
                            assert not measurement["overflowing"]
                        reopened.screenshot(path=str(artifacts / "compact-mobile.png"))
                        checks.append(
                            "Repeated desktop/narrow resizes keep source details "
                            "and the explicit choice within the viewport."
                        )
                        assert original == original_copy
                        assert not errors, errors
                        assert not external, external
                        remote.assert_not_called()
                        receipt["passed"] = True
                    finally:
                        browser.close()
                        resources["browser_closed"] = True
            finally:
                server.shutdown()
                server.app.close()
                server.server_close()
                thread.join(timeout=5)
                resources["server_closed"] = not thread.is_alive()
                receipt.update(
                    {
                        "checks": checks,
                        "page_errors": errors,
                        "external_requests": external,
                        "resources": resources,
                        "model_calls": remote.call_count,
                        "artifacts_sha256": {
                            path.name: hashlib.sha256(path.read_bytes()).hexdigest()
                            for path in artifacts.iterdir()
                            if path.is_file()
                        },
                    }
                )
                (artifacts / "receipt.json").write_text(
                    json.dumps(receipt, ensure_ascii=False, indent=2) + "\n"
                )
    print(f"PASS: {len(checks)} offline handover journeys. Receipt: {artifacts}")


if __name__ == "__main__":
    main()
