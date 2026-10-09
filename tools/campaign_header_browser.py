"""Fictional proof of compact, readable campaign headers and retained save recovery.

Exercises real local saves through the interface, including an acknowledgement
held while controls are locked and a successful save whose reply is deliberately
dropped. Exact messages, current work and one-request semantics remain inspectable.
No private workspace, provider, model, account or installed release is tested.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
import threading
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

from sinter import client  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import (  # noqa: E402
    CAMPAIGN_SAVED_MESSAGE,
    expect_campaign_message,
    launch_chromium,
    require_module,
)

THEME = "theme => document.documentElement.dataset.theme = theme"
HOLD_SAVE_ACK = """() => {
  window.headerFetchOriginal = window.fetch;
  window.fetch = async (path, options) => {
    const reply = await window.headerFetchOriginal(path, options);
    if (path === '/api/campaigns/save') {
      window.headerSavedReply = await reply.clone().json();
      await new Promise(resolve => window.headerReleaseSave = resolve);
    }
    return reply;
  };
}"""
RELEASE_SAVE_ACK = (
    "window.headerReleaseSave(); window.fetch = window.headerFetchOriginal"
)
HEADER_READY = """() => {
  const e = document.querySelector('.campaign-section-navigation');
  return e.getBoundingClientRect().top < 200;
}"""
HEADER_GEOMETRY = """() => {
  const rect = e => {
    const r = e.getBoundingClientRect();
    return {x:r.x, y:r.y, width:r.width, height:r.height, bottom:r.bottom};
  };
  const bar = document.querySelector('.campaign-save-bar');
  const navigation = document.querySelector('.campaign-section-navigation');
  const controls = [...bar.querySelectorAll('button'),
    ...navigation.querySelectorAll('[role=tab]')].map(e => ({
      label:e.textContent, ...rect(e),
      font:Number.parseFloat(getComputedStyle(e).fontSize)
    }));
  return {bar:rect(bar), navigation:rect(navigation), controls,
    occupiedBottom:Math.max(rect(bar).bottom,rect(navigation).bottom),
    overflow:document.documentElement.scrollWidth > innerWidth};
}"""


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--chromium", default=os.environ.get("SINTER_CHROMIUM"))
    parser.add_argument(
        "--output-dir", type=Path, help="New private evidence directory; never reused."
    )
    args = parser.parse_args(argv)
    if args.output_dir:
        args.output_dir = args.output_dir.expanduser().absolute()
        if not args.output_dir.parent.is_dir():
            parser.error("The output parent must exist.")
        if args.output_dir.exists() or args.output_dir.is_symlink():
            parser.error("Retain the existing output and choose a new directory.")
    require_module(
        parser,
        "playwright.sync_api",
        "Playwright",
        "python -m pip install '.[browser]'",
    )
    if args.chromium:
        try:
            args.chromium = str(Path(args.chromium).expanduser().resolve(strict=True))
        except (OSError, RuntimeError):
            parser.error("Choose an existing executable Chromium path.")
        if not Path(args.chromium).is_file() or not os.access(args.chromium, os.X_OK):
            parser.error("Choose an existing executable Chromium path.")
    return args


def write_json(path, value):
    """Publish a private complete receipt without replacing retained evidence."""
    raw = (
        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n"
    ).encode("utf-8")
    temporary = path.with_name(path.name + ".partial")
    descriptor = os.open(
        temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY | os.O_NOFOLLOW, 0o600
    )
    with os.fdopen(descriptor, "wb") as stream:
        stream.write(raw)
        stream.flush()
        os.fsync(stream.fileno())
    os.link(temporary, path)
    temporary.unlink()
    parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
    try:
        os.fsync(parent)
    finally:
        os.close(parent)


def screenshot(page, path):
    page.screenshot(path=str(path))
    path.chmod(0o600)


def fixture() -> dict:
    """Create operator-scale local correspondence with no invented commitments."""
    route = "Fictional research discussion"
    return {
        "title": "Fictional compact-header campaign",
        "organisation": "Fictional Workshop Association",
        "objective": "Retain exact records. No permission or funding is confirmed.",
        "opportunities": [
            {
                "name": route,
                "purpose": "research",
                "application_mode": "unknown",
                "status": "researching",
                "fit": "Fictional scope and unanswered question only.",
            }
        ],
        "communications": [
            {
                "opportunity": route,
                "subject": f"Fictional message {index + 1:02d}",
                "content": "Fictional source wording — café 中文 🧭 e\u0301. "
                "No agreement, permission, payment or award is established.",
                "direction": "incoming",
                "status": "received",
            }
            for index in range(47)
        ],
    }


def source_pins() -> dict[str, str]:
    paths = sorted(
        path
        for path in (ROOT / "src").rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )
    paths += [ROOT / "tools" / "_support.py", Path(__file__).resolve()]
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in paths
    }


def main(argv: list[str] | None = None) -> None:
    args = arguments(argv)
    from playwright.sync_api import expect, sync_playwright

    if args.output_dir:
        artifacts = args.output_dir
        artifacts.mkdir(mode=0o700)
    else:
        artifacts = Path(tempfile.mkdtemp(prefix="sinter-campaign-header-"))
    workspace = artifacts / "workspace"
    workspace.mkdir(mode=0o700)
    write_json(artifacts / "fixture-input.json", fixture())
    before = source_pins()
    cases, errors, external = [], [], []
    closed = {"contexts": False, "browser": False, "server": False}
    with nullcontext(str(workspace)) as data:
        with patch.object(
            client, "_open", side_effect=AssertionError("Offline only")
        ) as remote:
            server = make_server(port=0, directory=data)
            original = server.app.campaigns.save(fixture())
            write_json(artifacts / "initial-saved-campaign.json", original)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f"http://127.0.0.1:{server.server_port}"
            try:
                with sync_playwright() as driver:
                    browser = launch_chromium(driver, args.chromium)
                    try:
                        for theme, width, height in (
                            ("light", 390, 844),
                            ("dark", 390, 844),
                            ("light", 1265, 712),
                            ("dark", 1265, 712),
                        ):
                            name = f"{theme}-{width}x{height}"
                            record = {
                                "case": name,
                                "passed": False,
                                "context_closed": False,
                            }
                            cases.append(record)
                            context = browser.new_context(
                                viewport={"width": width, "height": height},
                                reduced_motion="reduce",
                                service_workers="block",
                            )
                            context.route(
                                "**/*",
                                lambda route: (
                                    route.continue_()
                                    if route.request.url.startswith(base + "/")
                                    else (
                                        external.append(route.request.url),
                                        route.abort(),
                                    )
                                ),
                            )
                            page = context.new_page()
                            page.set_default_timeout(9000)
                            page.on(
                                "pageerror", lambda error: errors.append(str(error))
                            )
                            posts = []
                            page.on(
                                "request",
                                lambda request: (
                                    posts.append(request.url)
                                    if request.method == "POST"
                                    else None
                                ),
                            )
                            try:
                                page.goto(base + "/#campaigns")
                                expect_campaign_message(
                                    page,
                                    "Most recently updated campaign opened.",
                                    exact=False,
                                )
                                page.evaluate(THEME, theme)
                                title = page.get_by_label("Campaign name", exact=True)
                                if not title.is_visible():
                                    page.get_by_text(
                                        "Campaign details", exact=True
                                    ).click()
                                edited = "Fictional confirmed save — " + name
                                title.fill(edited)
                                save = page.get_by_role(
                                    "button", name="Save campaign", exact=True
                                )
                                page.evaluate(HOLD_SAVE_ACK)
                                with page.expect_response(
                                    "**/api/campaigns/save"
                                ) as response:
                                    save.click()
                                assert response.value.status == 200
                                page.wait_for_function(
                                    "typeof window.headerReleaseSave === 'function'"
                                )
                                expect(save).to_be_disabled()
                                assert page.locator(".campaign-decision-card").evaluate(
                                    "e => e.inert"
                                )
                                assert page.locator(
                                    ".campaign-section-navigation"
                                ).evaluate("e => e.inert")
                                suggestion = page.get_by_role(
                                    "button", name="Add suggested action", exact=True
                                )
                                suggestion.dispatch_event("click")
                                page.evaluate(RELEASE_SAVE_ACK)
                                expect_campaign_message(page, CAMPAIGN_SAVED_MESSAGE)
                                acknowledged = page.evaluate("window.headerSavedReply")
                                record["acknowledged_saved_reply"] = acknowledged
                                write_json(
                                    artifacts / (name + "-confirmed-save.json"),
                                    acknowledged,
                                )
                                assert acknowledged["document"]["title"] == edited
                                assert acknowledged["document"]["actions"] == []
                                assert (
                                    acknowledged["document"]["communications"]
                                    == original["document"]["communications"]
                                )
                                read = page.get_by_role(
                                    "button", name="Read full message", exact=True
                                )
                                read.click()
                                dialog = page.get_by_role(
                                    "dialog", name="Campaign message", exact=True
                                )
                                expect(dialog).to_be_visible()
                                expect(
                                    dialog.get_by_role(
                                        "region",
                                        name="Complete campaign message",
                                        exact=True,
                                    )
                                ).to_have_text(CAMPAIGN_SAVED_MESSAGE)
                                dialog.get_by_role(
                                    "button", name="Close", exact=True
                                ).click()
                                expect(read).to_be_focused()
                                page.get_by_role(
                                    "tab", name="Communications", exact=True
                                ).click()
                                page.wait_for_function(HEADER_READY)
                                geometry = page.evaluate(HEADER_GEOMETRY)
                                record["routine_geometry"] = geometry
                                assert geometry["occupiedBottom"] <= (
                                    160 if width == 390 else 150
                                ), geometry
                                assert not geometry["overflow"]
                                for control in geometry["controls"]:
                                    assert (
                                        control["height"] >= 44
                                        and control["width"] >= 44
                                    ), control
                                    assert control["font"] >= 14, control
                                expect(
                                    page.locator(".campaign-communication")
                                ).to_have_count(47)
                                expect(
                                    page.locator(".campaign-save-state")
                                ).to_have_text("Saved on this computer")
                                expect(
                                    page.locator(".campaign-save-feedback")
                                ).to_be_hidden()
                                screenshot(page, artifacts / (name + "-routine.png"))
                                page.get_by_role(
                                    "tab", name="Opportunities", exact=True
                                ).click()
                                if not title.is_visible():
                                    page.get_by_text(
                                        "Campaign details", exact=True
                                    ).click()
                                uncertain_title = (
                                    "Fictional retained uncertain save — café 中文 🧭 "
                                    + name
                                )
                                title.fill(uncertain_title)

                                def lose_acknowledgement(route):
                                    reply = route.fetch()
                                    assert reply.ok
                                    record["uncertain_stored_reply"] = reply.json()
                                    route.abort("failed")

                                page.route(
                                    "**/api/campaigns/save", lose_acknowledgement
                                )
                                save.click()
                                feedback = page.locator(".campaign-save-feedback")
                                expect(
                                    feedback.locator(".notice.error")
                                ).to_be_visible()
                                expect(save).to_be_enabled()
                                expect(
                                    page.locator(".campaign-message-summary")
                                ).to_contain_text("Outcome unconfirmed")
                                complete = feedback.text_content()
                                assert "save may have finished" in complete
                                expect(title).to_have_value(uncertain_title)
                                read.click()
                                expect(
                                    dialog.get_by_role(
                                        "region",
                                        name="Complete campaign message",
                                        exact=True,
                                    )
                                ).to_have_text(complete)
                                dialog.get_by_role(
                                    "button", name="Close", exact=True
                                ).click()
                                expect(read).to_be_focused()
                                assert posts.count(base + "/api/campaigns/save") == 2, (
                                    posts
                                )
                                actual = server.app.campaigns.get(original["id"])
                                assert actual == record["uncertain_stored_reply"]
                                assert (
                                    actual["document"]["communications"]
                                    == original["document"]["communications"]
                                )
                                record.update(
                                    passed=True,
                                    acknowledgement=CAMPAIGN_SAVED_MESSAGE,
                                    uncertain_message=complete,
                                    posts=posts,
                                    no_request_replay=True,
                                    original_records_retained=True,
                                )
                                screenshot(page, artifacts / (name + "-recovery.png"))
                            except Exception as problem:
                                record["error"] = (
                                    type(problem).__name__ + ": " + str(problem)
                                )
                                try:
                                    screenshot(page, artifacts / (name + "-FAILED.png"))
                                except Exception:
                                    pass
                                raise
                            finally:
                                context.close()
                                record["context_closed"] = True
                        closed["contexts"] = True
                    finally:
                        closed["contexts"] = all(row["context_closed"] for row in cases)
                        browser.close()
                        closed["browser"] = True
            finally:
                server.shutdown()
                server.app.close()
                server.server_close()
                thread.join(timeout=5)
                closed["server"] = not thread.is_alive()
                after = source_pins()
                receipt = {
                    "schema": "sinter-fictional-campaign-header-browser/v1",
                    "source_root": str(ROOT),
                    "retained_workspace": str(workspace),
                    "source_hashes_before": before,
                    "source_hashes_after": after,
                    "source_unchanged": before == after,
                    "cases": cases,
                    "page_errors": errors,
                    "external_requests": external,
                    "model_calls": remote.call_count,
                    "closed": closed,
                    "scope": "Prospective fictional source UI; no installed "
                    "or customer-device acceptance.",
                }
                write_json(artifacts / "receipt.json", receipt)
                print(
                    json.dumps(
                        {
                            "artifacts": str(artifacts),
                            "cases": len(cases),
                            "closed": closed,
                        }
                    )
                )
            assert all(row["passed"] for row in cases) and len(cases) == 4
            assert not errors and not external and remote.call_count == 0
            assert before == after and all(closed.values())


if __name__ == "__main__":
    main()
