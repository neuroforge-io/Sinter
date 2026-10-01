"""Fictional local Word recovery when browser download delivery is suppressed.

This deliberately injected download denial is not a reproduction or diagnosis
of the user's IAB timeout. Real local files and their exact bytes are checked;
no actual IAB delivery, installed release or untested platform is qualified.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import sys
import tempfile
import threading
from contextlib import ExitStack
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from sinter import client  # noqa: E402
from sinter.docx_export import export_docx  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402

APPLIED_WORDING = (
    "# Fictional exact applied wording\n\nNo approval — 🐝 e\u0301.\n\n"
    '> Literal <img src="https://example.invalid/not-fetched">\n\n'
    "<!-- sinter:page-break -->\n\nSecond page stays exact."
)


def source_hashes():
    return {
        str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
        for p in sorted((ROOT / "src").rglob("*"))
        if p.is_file() and "__pycache__" not in p.parts
    }


def originals(app):
    return {
        "casebooks": [app.casebooks.get(x["id"]) for x in app.casebooks.list()],
        "campaigns": [app.campaigns.get(x["id"]) for x in app.campaigns.list()],
        "reports": [app.store.report(x["id"]) for x in app.store.reports()],
        "preferences": app.preferences.public(),
    }


def main(argv=None):
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    artifacts = Path(tempfile.mkdtemp(prefix="sinter-word-copy-proof-"))
    receipt = {
        "scope": (
            "Linux source-only, fictional local-copy recovery; no IAB delivery claim"
        ),
        "checks": [],
        "errors": [],
        "external_requests": [],
        "downloads": [],
        "requests": [],
        "saved_files": [],
        "resources": [],
        "source_before": source_hashes(),
        "harness_completed": False,
    }
    checks = receipt["checks"]

    def check(name, passed, detail=None):
        checks.append({"check": name, "passed": bool(passed), "detail": detail})
        assert passed, name

    with (
        tempfile.TemporaryDirectory(prefix="workspace-", dir=artifacts) as directory,
        ExitStack() as guards,
    ):
        for name in ["chat", "search", "_open", "_get", "_post"]:
            guards.enter_context(
                patch.object(
                    client, name, side_effect=AssertionError("No hosted " + name)
                )
            )
        server = make_server(port=0, directory=directory)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        server_closed = False
        try:
            with sync_playwright() as pw:
                browser = launch_chromium(pw, args.chromium)
                try:
                    base = f"http://127.0.0.1:{server.server_port}"
                    for width in (1440, 390):
                        for workflow in ("casebook", "campaign"):
                            prefix = f"{workflow}-{width}-"
                            context = browser.new_context(
                                viewport={
                                    "width": width,
                                    "height": 1000 if width == 1440 else 844,
                                },
                                reduced_motion="reduce",
                            )
                            try:

                                def restrict(route):
                                    if route.request.url.startswith(base + "/"):
                                        route.continue_()
                                    else:
                                        receipt["external_requests"].append(
                                            route.request.url
                                        )
                                        route.abort()

                                context.route("**/*", restrict)
                                page = context.new_page()
                                page.set_default_timeout(8000)
                                page.on(
                                    "pageerror",
                                    lambda error: receipt["errors"].append(str(error)),
                                )
                                page.on(
                                    "download",
                                    lambda download: receipt["downloads"].append(
                                        download.suggested_filename
                                    ),
                                )
                                page.on("dialog", lambda dialog: dialog.accept())
                                page.on(
                                    "request",
                                    lambda request: (
                                        receipt["requests"].append(
                                            {
                                                "path": request.url.removeprefix(base),
                                                "payload": request.post_data_json,
                                            }
                                        )
                                        if request.url.endswith(
                                            "/api/documents/docx/save"
                                        )
                                        else None
                                    ),
                                )
                                page.add_init_script("""window.deniedWordDownloads=[];
                                  const click=HTMLAnchorElement.prototype.click;
                                  HTMLAnchorElement.prototype.click=function(){
                                    if(this.download){window.deniedWordDownloads.push(this.download);return;}
                                    return click.call(this);};
                                  Object.defineProperty(navigator,'clipboard',{value:{
                                    writeText:async()=>{throw new DOMException(
                                      'Synthetic clipboard denial','NotAllowedError');}
                                    }});""")
                                if workflow == "casebook":
                                    page.goto(base + "/#casebooks")
                                    page.get_by_role(
                                        "button",
                                        name="Try a fictional community example",
                                    ).click()
                                    page.get_by_label(
                                        "Prepare a", exact=True
                                    ).select_option("handover")
                                    page.get_by_role(
                                        "button",
                                        name="Prepare source-only report",
                                        exact=True,
                                    ).click()
                                    editor_label, edit_name, word_name = (
                                        "Edit your draft",
                                        "Edit draft",
                                        "Download Word (.docx)",
                                    )
                                else:
                                    title = f"Fictional Word recovery {width}"
                                    server.app.campaigns.save(
                                        {
                                            "title": title,
                                            "organisation": "Fictional association",
                                            "objective": (
                                                "No grant or order has been approved."
                                            ),
                                            "opportunities": [],
                                        }
                                    )
                                    page.goto(base + "/#campaigns")
                                    expect(
                                        page.get_by_label("Campaign name", exact=True)
                                    ).to_have_value(title)
                                    page.get_by_role(
                                        "button",
                                        name="Prepare campaign brief",
                                        exact=True,
                                    ).click()
                                    editor_label, edit_name, word_name = (
                                        "Edit the decision brief",
                                        "Edit decision brief",
                                        "Download Word brief (.docx)",
                                    )
                                report = page.get_by_role(
                                    "region", name="Your draft report"
                                )
                                expect(report).to_be_visible()
                                before = originals(server.app)
                                source_records = json.dumps(
                                    before, ensure_ascii=False, sort_keys=True
                                )
                                menu = report.locator(".export-menu")
                                menu.locator("summary").click()
                                report.get_by_role(
                                    "button", name=edit_name, exact=True
                                ).click()
                                applied = APPLIED_WORDING
                                report.get_by_label(editor_label, exact=True).fill(
                                    applied
                                )
                                report.locator(
                                    ".document-word-save-options > summary"
                                ).click()
                                local_save = report.get_by_role(
                                    "button",
                                    name="Save Word copy on this computer",
                                    exact=True,
                                )
                                count = len(receipt["requests"])
                                local_save.click()
                                expect(
                                    report.locator(".document-feedback")
                                ).to_contain_text("Apply or cancel")
                                check(
                                    prefix
                                    + "pending-edits-refuse-save-without-request",
                                    len(receipt["requests"]) == count
                                    and report.get_by_label(
                                        editor_label, exact=True
                                    ).input_value()
                                    == applied,
                                )
                                report.get_by_role(
                                    "button", name="Apply edits", exact=True
                                ).click()
                                report.get_by_role(
                                    "button", name=word_name, exact=True
                                ).click()
                                expect(
                                    report.locator(".document-feedback")
                                ).to_contain_text("download requested")
                                check(
                                    prefix + "normal-download-request-remains-honest",
                                    len(receipt["downloads"]) == 0
                                    and page.evaluate(
                                        "window.deniedWordDownloads.length"
                                    )
                                    >= 1,
                                )
                                local_save.click()
                                path_control = report.get_by_label(
                                    "Saved Word file path", exact=True
                                )
                                expect(path_control).not_to_have_value("")
                                path = Path(path_control.input_value())
                                payload = receipt["requests"][-1]["payload"]
                                expected = export_docx(payload).content
                                check(
                                    prefix + "actual-local-file-exact-applied-text",
                                    path.is_relative_to(Path(directory) / "exports")
                                    and path.read_bytes() == expected
                                    and payload["markdown"] == applied,
                                )
                                check(
                                    prefix
                                    + "originals-reviews-reports-preferences-retained",
                                    json.dumps(
                                        originals(server.app),
                                        ensure_ascii=False,
                                        sort_keys=True,
                                    )
                                    == source_records,
                                )
                                report.get_by_role(
                                    "button", name="Copy saved file path", exact=True
                                ).click()
                                expect(
                                    report.locator(".document-feedback")
                                ).to_contain_text("path is selected")
                                check(
                                    prefix + "clipboard-denial-retains-selectable-path",
                                    path_control.input_value() == str(path)
                                    and path_control.evaluate(
                                        "el=>el.selectionStart===0&&el.selectionEnd===el.value.length"
                                    ),
                                )
                                first = path
                                local_save.click()
                                expect(path_control).not_to_have_value(str(first))
                                second = Path(path_control.input_value())
                                check(
                                    prefix + "explicit-repeat-distinct-no-overwrite",
                                    second.read_bytes() == expected
                                    and first.read_bytes() == expected
                                    and second != first,
                                )

                                # The real save has deliberately lost confirmation.
                                # No automatic replay is permitted.
                                def uncertain(route):
                                    result = route.fetch()
                                    route.fulfill(
                                        status=503,
                                        content_type="application/json",
                                        body=json.dumps(
                                            {"error": "Synthetic confirmation lost"}
                                        ),
                                    )
                                    result.dispose()

                                context.route("**/api/documents/docx/save", uncertain)
                                old_count = len(receipt["requests"])
                                old_files = set(
                                    (Path(directory) / "exports").glob("*.docx")
                                )
                                local_save.click()
                                expect(
                                    report.locator(".document-feedback")
                                ).to_contain_text("not confirmed")
                                expect(
                                    report.locator(".document-local-copy")
                                ).to_contain_text("Previously confirmed copy")
                                check(
                                    prefix
                                    + "interrupted-confirmation-honest-with-prior-path",
                                    len(receipt["requests"]) == old_count + 1
                                    and path_control.input_value() == str(second)
                                    and len(
                                        set(
                                            (Path(directory) / "exports").glob("*.docx")
                                        )
                                        - old_files
                                    )
                                    == 1,
                                )
                                page.wait_for_timeout(100)
                                check(
                                    prefix + "no-automatic-save-replay",
                                    len(receipt["requests"]) == old_count + 1,
                                )
                                context.unroute("**/api/documents/docx/save", uncertain)

                                held = []

                                def hold(route):
                                    held.append((route, route.fetch()))

                                context.route("**/api/documents/docx/save", hold)
                                local_save.click()
                                expect(local_save).to_be_disabled()
                                if not menu.evaluate("el=>el.open"):
                                    menu.locator("summary").click()
                                report.get_by_role(
                                    "button", name=edit_name, exact=True
                                ).click()
                                later = (
                                    applied + "\n\nLater pending wording is retained."
                                )
                                report.get_by_label(editor_label, exact=True).fill(
                                    later
                                )
                                assert len(held) == 1
                                held[0][0].fulfill(response=held[0][1])
                                held[0][1].dispose()
                                expect(local_save).to_be_enabled()
                                expect(
                                    report.locator(".document-local-copy")
                                ).to_contain_text("Earlier saved copy")
                                late_path = Path(path_control.input_value())
                                check(
                                    prefix + "held-save-retains-clicked-snapshot",
                                    late_path.read_bytes() == expected
                                    and report.get_by_label(
                                        editor_label, exact=True
                                    ).input_value()
                                    == later,
                                )
                                context.unroute("**/api/documents/docx/save", hold)
                                report.get_by_role(
                                    "button", name="Apply edits", exact=True
                                ).click()
                                expect(
                                    report.locator(".document-local-copy")
                                ).to_contain_text("Earlier saved copy")
                                local_save.click()
                                expect(path_control).not_to_have_value(str(late_path))
                                final_path = Path(path_control.input_value())
                                check(
                                    prefix
                                    + "explicit-new-applied-snapshot-saved-separately",
                                    final_path.read_bytes()
                                    == export_docx(
                                        receipt["requests"][-1]["payload"]
                                    ).content
                                    and receipt["requests"][-1]["payload"]["markdown"]
                                    == later
                                    and late_path.read_bytes() == expected,
                                )
                                check(
                                    prefix + "local-work-still-unchanged",
                                    json.dumps(
                                        originals(server.app),
                                        ensure_ascii=False,
                                        sort_keys=True,
                                    )
                                    == source_records,
                                )
                                check(
                                    prefix + "phone-layout-bounded",
                                    page.evaluate(
                                        "()=>document.documentElement.scrollWidth<=innerWidth+1"
                                    ),
                                )
                                page.screenshot(
                                    path=str(
                                        artifacts / (prefix + "saved-local-path.png")
                                    ),
                                    animations="disabled",
                                )
                            finally:
                                context.close()
                                receipt["resources"].append(
                                    {"context": prefix, "closed": True}
                                )
                finally:
                    browser.close()
                    receipt["resources"].append({"browser_closed": True})
            persisted = {
                str(path): hashlib.sha256(path.read_bytes()).hexdigest()
                for path in (Path(directory) / "exports").glob("*.docx")
            }
            for path, digest in persisted.items():
                destination = artifacts / "saved-copies" / Path(path).name
                destination.parent.mkdir(exist_ok=True)
                shutil.copy2(path, destination)
                receipt["saved_files"].append(
                    {
                        "original_path": path,
                        "capture": str(destination),
                        "sha256": digest,
                    }
                )
            state = originals(server.app)
            server.shutdown()
            server.app.close()
            server.server_close()
            thread.join(timeout=5)
            server_closed = True
            receipt["resources"].append(
                {"server_closed": True, "thread_stopped": not thread.is_alive()}
            )
            reopened = make_server(port=0, directory=directory)
            try:
                check(
                    "close-reopen-retains-real-copies",
                    all(
                        Path(path).is_file()
                        and hashlib.sha256(Path(path).read_bytes()).hexdigest()
                        == digest
                        for path, digest in persisted.items()
                    ),
                )
                check(
                    "close-reopen-retains-original-local-work",
                    originals(reopened.app) == state,
                )
            finally:
                reopened.app.close()
                reopened.server_close()
                receipt["resources"].append({"reopened_app_closed": True})
            receipt["harness_completed"] = True
        except Exception as error:
            receipt["harness_error"] = f"{type(error).__name__}: {error}"
        finally:
            if not server_closed:
                server.shutdown()
                server.app.close()
                server.server_close()
                thread.join(timeout=5)
                receipt["resources"].append(
                    {"server_closed": True, "thread_stopped": not thread.is_alive()}
                )
    receipt["source_after"] = source_hashes()
    receipt["source_unchanged"] = receipt["source_before"] == receipt["source_after"]
    receipt["passed"] = (
        receipt["harness_completed"]
        and all(x["passed"] for x in checks)
        and not receipt["errors"]
        and not receipt["external_requests"]
        and receipt["source_unchanged"]
    )
    path = artifacts / "receipt.json"
    path.write_text(json.dumps(receipt, ensure_ascii=False, indent=2) + "\n")
    print(path)
    print(f"{sum(x['passed'] for x in checks)}/{len(checks)} checks passed.")
    if not receipt["passed"]:
        raise SystemExit(1)
    return receipt


if __name__ == "__main__":
    main()
