"""Measure the same fictional communications operations against an explicit source.

Use fresh output directories for each sequential A/B/B/A run. Timings include the
browser driver and assertions; this does not qualify an installed release or make
a hardware, customer acceptance or whole-product quality claim.
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import importlib.metadata
import json
import os
import platform
import signal
import statistics
import subprocess
import sys
import threading
import time
from collections import defaultdict
from pathlib import Path
from unittest.mock import patch
from urllib.parse import urlsplit

TITLE = "Fictional communications comparison — 47 records"
VIEWPORT = {"width": 1440, "height": 1000}
COUNTS = {"communications": 47, "sources": 76, "routes": 12}
TARGET_CHARACTERS = 170_000
EDIT_INDEX = 46


def digest(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def encoded(value: object) -> bytes:
    return (json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False) + "\n").encode("utf-8")


def exclusive_json(path: Path, value: object) -> None:
    """Publish complete private bytes without replacing any earlier artifact."""
    temporary = path.with_name(path.name + ".partial")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(encoded(value))
            stream.flush()
            os.fsync(stream.fileno())
        os.link(temporary, path)
        temporary.unlink()
        parent = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(parent)
        finally:
            os.close(parent)
    except BaseException:
        # A partial file remains evidence; never overwrite it or an existing receipt.
        raise


def character_count(value: object) -> int:
    if isinstance(value, str):
        return len(value)
    if isinstance(value, list):
        return sum(character_count(item) for item in value)
    if isinstance(value, dict):
        return sum(character_count(item) for item in value.values())
    return 0


def wording(size: int, label: str) -> str:
    sentence = label + " Fictional only. Funding, authority, owners and IP permissions are unconfirmed. "
    return (sentence * (size // len(sentence) + 1))[:size]


def fixture(validate_document) -> dict:
    """One fixed workload, shared across old/new sources and every matched run."""
    sources = [
        {"id": f"{index + 1:032x}", "title": f"Fictional evidence source {index:02d}",
         "url": f"https://example.invalid/record/{index:02d}", "checked_at": "2026-10-09",
         "notes": wording(1050, f"Source {index:02d}.")}
        for index in range(COUNTS["sources"])
    ]
    routes = [{"name": f"Fictional route {index:02d}", "status": "clarification"}
              for index in range(COUNTS["routes"])]
    messages = []
    for index in range(COUNTS["communications"]):
        status = ("received", "sent", "draft")[index % 3]
        source = sources[index]
        messages.append({
            "subject": f"Fictional CommToken-{index:02d} record",
            "counterparty": f"Fictional contact {index % 5:02d}",
            "opportunity": routes[index % len(routes)]["name"],
            "date": "" if index % 7 == 0 or status == "draft" else f"2026-09-{1 + index % 28:02d}",
            "direction": "incoming" if status == "received" else "outgoing",
            "status": status, "channel": "email",
            "content": wording(1100, f"Message {index:02d}; CorpusNeedle-{index:02d}🐝; café e\u0301."),
            "evidence_links": [{
                "source_id": source["id"], "title": source["title"], "url": source["url"],
                "checked_at": source["checked_at"],
                "notes": f"SavedSnapshot-{index:02d}; fictional original wording, not a current approval.",
            }],
        })
    document = validate_document({
        "title": TITLE, "organisation": "Fictional Community Association",
        "objective": "Retain correspondence and draft follow-ups. No commitments are confirmed.",
        "sources": sources, "opportunities": routes, "communications": messages,
    })
    remaining = TARGET_CHARACTERS - character_count(document)
    assert remaining >= 0, "The fixed workload exceeds its intended text size."
    for index, source in enumerate(document["sources"]):
        added = min(remaining, 6000 - len(source["notes"]))
        source["notes"] += wording(added, f"Fictional retained source wording {index:02d}.")
        remaining -= added
        if not remaining:
            break
    assert remaining == 0
    document = validate_document(document)
    assert character_count(document) == TARGET_CHARACTERS
    assert len(document["communications"]) == COUNTS["communications"]
    assert len(document["sources"]) == COUNTS["sources"]
    assert len(document["opportunities"]) == COUNTS["routes"]
    assert len(encoded(document)) < 1_000_000
    return document


def source_hashes(root: Path) -> dict[str, dict]:
    """Pin exact runtime/UI bytes with portable, source-relative inventory keys."""
    paths = [path for path in (root / "src/sinter").rglob("*")
             if path.is_file() and "__pycache__" not in path.parts
             and path.suffix != ".pyc"]
    paths += [root / name for name in ("VERSION", "pyproject.toml") if (root / name).is_file()]
    result = {}
    for path in sorted(paths):
        if path.is_symlink() or path.stat().st_size > 8 * 1024 * 1024:
            raise ValueError("Runtime source contains a redirected or unexpectedly large file: " + str(path))
        raw = path.read_bytes()
        result[path.relative_to(root).as_posix()] = {"bytes": len(raw), "sha256": digest(raw)}
    return result


def git_identity(root: Path) -> dict:
    if not (root / ".git").exists():
        return {"available": False, "reason": "Source snapshot has no Git metadata; use its file pins."}
    result = {"available": True}
    for key, arguments in (("head", ["rev-parse", "HEAD"]), ("status", ["status", "--porcelain"])):
        try:
            command = subprocess.run(["git", *arguments], cwd=root, capture_output=True,
                                     text=True, timeout=10, check=False)
            result[key] = command.stdout.strip()
            result[key + "_exit_code"] = command.returncode
        except (OSError, subprocess.TimeoutExpired) as problem:
            result[key + "_error"] = type(problem).__name__ + ": " + str(problem)[:600]
    return result


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-root", type=Path, required=True,
                        help="Exact source tree to import and serve; do not use a real workspace.")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="New private directory, created exclusively; never reused or overwritten.")
    parser.add_argument("--chromium", type=Path, default=os.environ.get("SINTER_CHROMIUM"),
                        help="Existing Chromium executable; otherwise use Playwright's installed browser.")
    parser.add_argument("--samples", type=int, choices=range(1, 6), default=3,
                        help="Retain 1–5 samples per repeated operation (default3).")
    args = parser.parse_args(argv)
    args.source_root = args.source_root.expanduser().resolve(strict=True)
    if not (args.source_root / "src/sinter/server.py").is_file():
        parser.error("--source-root must contain src/sinter/server.py.")
    args.output_dir = args.output_dir.expanduser().absolute()
    if not args.output_dir.parent.is_dir():
        parser.error("The output parent must already exist.")
    if args.output_dir.exists() or args.output_dir.is_symlink():
        parser.error("--output-dir already exists; retain it and choose a new directory.")
    if args.chromium:
        args.chromium = args.chromium.expanduser().resolve(strict=True)
        if not args.chromium.is_file() or not os.access(args.chromium, os.X_OK):
            parser.error("Choose an existing executable Chromium path.")
    return args


def main(argv=None) -> int:
    args = arguments(argv)
    os.mkdir(args.output_dir, 0o700)
    workspace = args.output_dir / "fictional-workspace"
    workspace.mkdir(mode=0o700)
    sys.dont_write_bytecode = True
    # The harness itself is shared. Every product import comes from the selected tree.
    sys.path[:0] = [str(args.source_root / "src"), str(args.source_root)]
    samples, failures, page_errors, external, checks, dom_observations = [], [], [], [], [], []
    resources = {"browser_closed": False, "server_closed": False, "context_closed": False}
    receipt = {"passed": False, "schema": "sinter-fictional-communications-profile/v1"}
    harness_before = digest(Path(__file__).read_bytes())
    server = thread = browser = context = page = None
    before = after = document = expected = None
    model_calls, browser_version = 0, "not started"
    closing = False
    signals = []
    original_handlers = {}

    def interrupted(number, _frame):
        signals.append(number)
        if not closing:
            raise InterruptedError(f"Received signal{number}; no request will be automatically replayed.")

    for number in (signal.SIGINT, signal.SIGTERM):
        original_handlers[number] = signal.signal(number, interrupted)

    def failed(phase, problem):
        failures.append({"phase": phase, "error": type(problem).__name__ + ": " + str(problem)[:3000]})

    def measured(name, sample, action):
        started = time.perf_counter_ns()
        row = {"operation": name, "sample": sample, "passed": False}
        try:
            value = action()
            row["passed"] = True
            if isinstance(value, (str, int, float, bool, dict, list)):
                row["observation"] = value
            return value
        except (Exception, KeyboardInterrupt) as problem:
            row["error"] = type(problem).__name__ + ": " + str(problem)[:1800]
            raise
        finally:
            row["milliseconds"] = round((time.perf_counter_ns() - started) / 1e6, 3)
            samples.append(row)
            print(json.dumps(row, ensure_ascii=True), flush=True)

    try:
        before = source_hashes(args.source_root)
        exclusive_json(args.output_dir / "started.json", {
            "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
            "source_root": str(args.source_root), "source_files": before,
            "harness_sha256": harness_before,
            "git": git_identity(args.source_root), "pid": os.getpid(),
            "workspace": str(workspace), "fixture_only": True,
        })
        from playwright.sync_api import expect, sync_playwright
        from sinter import client
        from sinter.campaigns import validate
        from sinter.server import make_server

        for module in (client, sys.modules["sinter.campaigns"], sys.modules["sinter.server"]):
            if not Path(module.__file__).resolve().is_relative_to(args.source_root / "src"):
                raise AssertionError("A product module was imported from a different source tree.")
        document = fixture(validate)
        expected = copy.deepcopy(document)
        fixture_path = args.output_dir / "fixture.json"
        exclusive_json(fixture_path, document)
        exclusive_json(args.output_dir / "expected-initial.json", expected)

        with patch.object(client, "_open", side_effect=AssertionError("Hosted requests are forbidden in this fictional benchmark.")) as remote:
            try:
                server = make_server(port=0, directory=workspace)
                thread = threading.Thread(target=server.serve_forever, daemon=True,
                                          name="sinter-fictional-communications-server")
                thread.start()
                base = f"http://127.0.0.1:{server.server_port}"
                origin = urlsplit(base)
                with sync_playwright() as driver:
                    try:
                        browser = driver.chromium.launch(headless=True,
                            executable_path=str(args.chromium) if args.chromium else None)
                        browser_version = browser.version

                        def new_page():
                            nonlocal context, page
                            context = browser.new_context(viewport=VIEWPORT, reduced_motion="reduce")

                            def route_request(route):
                                target = urlsplit(route.request.url)
                                if (target.scheme, target.hostname, target.port) == (origin.scheme, origin.hostname, origin.port):
                                    route.continue_()
                                else:
                                    external.append(route.request.url)
                                    route.abort()

                            context.route("**/*", route_request)
                            page = context.new_page()
                            page.set_default_timeout(10_000)
                            page.on("pageerror", lambda error: page_errors.append(str(error)))
                            return page

                        def ready():
                            expect(page.get_by_label("Campaign name", exact=True)).to_have_value(TITLE)
                            expect(page.get_by_role("button", name="Save campaign", exact=True)).to_be_enabled()
                            expect(page.locator(".campaign-save-state")).to_have_text("Saved on this computer")

                        def save():
                            with page.expect_response("**/api/campaigns/save") as save_response:
                                page.get_by_role("button", name="Save campaign", exact=True).click()
                            assert save_response.value.status == 200, save_response.value.status
                            expect(page.locator(".campaign-save-feedback")).to_have_text("Campaign saved. Answers, costs, checks and actions will be here when you return.")
                            ready()

                        def indexes():
                            return page.locator(".campaign-communication:visible").evaluate_all(
                                "cards => cards.map(card => Number(card.dataset.communicationIndex))")

                        def expect_indexes(wanted):
                            expect(page.locator(".campaign-communication:visible")).to_have_count(len(wanted))
                            assert indexes() == wanted, (indexes(), wanted)

                        def controls(label):
                            value = page.locator(".campaign-communication").evaluate_all("""cards => {
                              const rendered = control => {
                                if (control.closest('[hidden]')) return false;
                                for (let ancestor = control.parentElement; ancestor; ancestor = ancestor.parentElement) {
                                  if (ancestor.tagName === 'DETAILS' && !ancestor.open) {
                                    const summary = [...ancestor.children].find(child => child.tagName === 'SUMMARY');
                                    if (!summary?.contains(control)) return false;
                                  }
                                }
                                const style = getComputedStyle(control);
                                return style.display !== 'none' && style.visibility !== 'hidden'
                                  && style.visibility !== 'collapse' && control.getClientRects().length > 0;
                              };
                              return {
                              records: cards.length,
                              openRecords: cards.filter(card => card.querySelector('details')?.open).length,
                              allControls: cards.reduce((n,card) => n + card.querySelectorAll('input,textarea,select,button').length, 0),
                              visibleControls: cards.reduce((n,card) => n + [...card.querySelectorAll('input,textarea,select,button')].filter(rendered).length, 0)
                            }; }""")
                            if label.startswith("collapsed"):
                                assert value["openRecords"] == 0 and value["visibleControls"] == 0, value
                            if label.startswith("expanded"):
                                assert value["openRecords"] == 1 and value["visibleControls"] > 0, value
                            dom_observations.append({"phase": label, **value})
                            return value

                        def row():
                            return page.locator(f'.campaign-communication[data-communication-index="{EDIT_INDEX}"]')

                        def expand():
                            details = row().locator("details").first
                            if details.get_attribute("open") is None:
                                details.locator("summary").click()
                            expect(row().get_by_label("Message text or summary", exact=True)).to_have_value(expected["communications"][EDIT_INDEX]["content"])

                        new_page()
                        measured("empty_navigation", 1, lambda: page.goto(base + "/#campaigns"))
                        expect(page.locator(".campaign-save-bar")).to_be_visible()
                        for sample in range(1, 6):
                            measured("driver_readonly_roundtrip", sample, lambda: page.evaluate("document.readyState"))
                        page.get_by_text("Import or back up a campaign", exact=True).click()

                        def import_fixture():
                            page.get_by_label("Import campaign backup", exact=True).set_input_files(fixture_path)
                            expect(page.get_by_label("Campaign name", exact=True)).to_have_value(TITLE)
                            expect(page.locator(".campaign-save-feedback")).to_contain_text("Campaign imported locally.")

                        measured("import_complete_fixture", 1, import_fixture)
                        measured("initial_save", 1, save)
                        saved_id = server.app.campaigns.list()[0]["id"]

                        def exact_saved():
                            actual = server.app.campaigns.get(saved_id)["document"]
                            assert actual == expected, "The saved campaign differs from the complete expected document."
                            return actual

                        exact_saved()
                        for sample in range(1, args.samples + 1):
                            page.get_by_role("tab", name="Opportunities", exact=True).click()

                            def communications_tab():
                                page.get_by_role("tab", name="Communications", exact=True).click()
                                expect_indexes(list(range(COUNTS["communications"])))

                            measured("communications_tab_render", sample, communications_tab)
                            measured("collapsed_controls_observation", sample, lambda: controls(f"collapsed{sample}"))
                            measured("expand_one_complete_record", sample, expand)
                            measured("expanded_controls_observation", sample, lambda: controls(f"expanded{sample}"))
                            row().locator("summary").first.click()
                            search = page.get_by_label("Find a communication", exact=True)

                            def message_search():
                                search.fill(f"CorpusNeedle-{EDIT_INDEX:02d}🐝")
                                expect_indexes([EDIT_INDEX])

                            measured("search_full_saved_message", sample, message_search)

                            def evidence_search():
                                search.fill(f"SavedSnapshot-{EDIT_INDEX:02d}")
                                expect_indexes([EDIT_INDEX])

                            measured("search_saved_evidence_snapshot", sample, evidence_search)

                            def no_match():
                                search.fill("FictionalNoRecordsMatchThisLiteral")
                                expect_indexes([])

                            measured("search_no_match", sample, no_match)

                            def clear_search():
                                page.get_by_role("button", name="Clear communication filters", exact=True).click()
                                expect_indexes(list(range(COUNTS["communications"])))

                            measured("clear_search", sample, clear_search)

                            def scope():
                                page.get_by_label("Communication scope", exact=True).select_option("route:2")
                                expect_indexes([index for index in range(47) if index % 12 == 2])

                            measured("filter_one_route", sample, scope)
                            clear_search()
                            newest = sorted(range(47), key=lambda index: (
                                not bool(expected["communications"][index]["date"]),
                                -int(expected["communications"][index]["date"].replace("-", "") or 0), index))

                            def sort():
                                page.get_by_label("Communication order", exact=True).select_option("newest")
                                expect_indexes(newest)

                            measured("sort_recorded_dates_undated_last", sample, sort)
                            exact_saved()
                            page.get_by_label("Communication order", exact=True).select_option("record")
                            expect_indexes(list(range(47)))

                        checks.append("Search, scope, chronological order and expansion preserve every saved record and snapshot.")
                        for sample in range(1, args.samples + 1):
                            expand()
                            evidence = row().get_by_role("article", name="Communication evidence link")
                            picker = evidence.get_by_label("Link to a saved campaign source", exact=True)
                            chosen = expected["sources"][75 if sample % 2 else 74]
                            picker.fill("")
                            expect(evidence.locator(".campaign-source-matches button")).to_have_count(8)

                            def source_search():
                                picker.fill(chosen["title"])
                                expect(evidence.locator(".campaign-source-matches button")).to_have_count(1)

                            measured("search_registered_source", sample, source_search)

                            def link_source():
                                evidence.locator(f'button[data-campaign-source-id="{chosen["id"]}"]').click()
                                expect(evidence.get_by_label("Evidence link", exact=True)).to_have_value(chosen["url"])
                                expect(evidence.get_by_label("Evidence title", exact=True)).to_have_value(chosen["title"])

                            measured("explicit_source_link", sample, link_source)
                            expected["communications"][EDIT_INDEX]["evidence_links"][0].update(
                                {key: chosen[key] for key in ("title", "url", "checked_at")}, source_id=chosen["id"])
                            changed_text = document["communications"][EDIT_INDEX]["content"] + f"\nFictional local edit {sample}: <img src=x onerror=alert('never')> & café 🐝."

                            def safe_edit():
                                row().get_by_label("Message text or summary", exact=True).fill(changed_text)
                                expect(row().get_by_label("Message text or summary", exact=True)).to_have_value(changed_text)
                                assert row().locator("img[src=x]").count() == 0
                                expect(page.locator(".campaign-save-state")).to_have_text("Unsaved changes")

                            measured("literal_unicode_safe_edit", sample, safe_edit)
                            expected["communications"][EDIT_INDEX]["content"] = changed_text
                            measured("save_complete_document", sample, save)
                            exact_saved()
                            context.close()
                            context = None

                            def reopen():
                                new_page()
                                page.goto(base + "/#campaigns")
                                ready()
                                page.get_by_role("tab", name="Communications", exact=True).click()
                                expect_indexes(list(range(47)))
                                expand()
                                expect(row().get_by_label("Evidence link", exact=True)).to_have_value(chosen["url"])
                                expect(row().get_by_label("Evidence note", exact=True)).to_have_value(document["communications"][EDIT_INDEX]["evidence_links"][0]["notes"])

                            measured("fresh_context_reopen_exact_edit_and_link", sample, reopen)
                            exact_saved()
                        checks.append("Explicit link and literal Unicode edits save/reopen exactly; all original inputs and unrelated snapshots remain equal.")
                        exclusive_json(args.output_dir / "expected-final.json", expected)
                        exclusive_json(args.output_dir / "actual-final.json", exact_saved())
                        page.screenshot(path=str(args.output_dir / "communications-final.png"), animations="disabled")
                        os.chmod(args.output_dir / "communications-final.png", 0o600)
                        remote.assert_not_called()
                        assert not page_errors and not external
                        receipt["passed"] = True
                    except (Exception, KeyboardInterrupt) as problem:
                        failed("browser_workflow", problem)
                        if page:
                            try:
                                page.screenshot(path=str(args.output_dir / "failure.png"), animations="disabled", timeout=3000)
                                os.chmod(args.output_dir / "failure.png", 0o600)
                            except Exception as screenshot_error:
                                failed("failure_screenshot", screenshot_error)
                    finally:
                        closing = True
                        for label, resource in (("context", context), ("browser", browser)):
                            if resource:
                                try:
                                    resource.close()
                                    resources[label + "_closed"] = True
                                except Exception as problem:
                                    failed(label + "_cleanup", problem)
                            elif label == "context" and browser:
                                resources["context_closed"] = True
            finally:
                closing = True
                model_calls = remote.call_count
                if server:
                    try:
                        if thread and thread.is_alive():
                            server.shutdown()
                            thread.join(timeout=5)
                        server.app.close()
                        server.server_close()
                        resources["server_closed"] = not thread or not thread.is_alive()
                    except Exception as problem:
                        failed("server_cleanup", problem)
    except (Exception, KeyboardInterrupt) as problem:
        failed("setup_or_owner", problem)
    finally:
        closing = True
        try:
            after = source_hashes(args.source_root)
        except Exception as problem:
            failed("final_source_hashes", problem)
        for number, previous in original_handlers.items():
            signal.signal(number, previous)

    grouped = defaultdict(list)
    for row in samples:
        if row["passed"]:
            grouped[row["operation"]].append(row["milliseconds"])
    harness_after = digest(Path(__file__).read_bytes())
    receipt.update({
        "source_root": str(args.source_root), "source_files_before": before,
        "source_files_after": after, "source_unchanged_during_run": before is not None and before == after,
        "git_after": git_identity(args.source_root), "harness_sha256": harness_before,
        "harness_sha256_after": harness_after, "harness_unchanged_during_run": harness_before == harness_after,
        "fixture_only": True, "fixture": {**COUNTS, "normalized_string_code_points": character_count(document),
            "sha256": digest(encoded(document)) if document is not None else None},
        "browser": {"version": browser_version, "executable": str(args.chromium) if args.chromium else "Playwright installed Chromium",
                    "headless": True, "viewport": VIEWPORT},
        "python": sys.version.split()[0], "platform": platform.platform(),
        "playwright": importlib.metadata.version("playwright") if "playwright" in sys.modules else None,
        "methodology": {
            "timer": "Host perf_counter_ns includes every driver call, actionability wait and stated assertion. No warmup or outlier is discarded.",
            "sequence": "Same shared fixture and common old/new controls; run A/B/B/A sequentially into four new output directories.",
            "fresh_context": "Empty browser cookies/cache in a new context; same running browser/server and warm host filesystem. Not an installed cold start.",
            "overhead": "Five readonly driver roundtrips retained separately, never subtracted.",
            "scope": "Source-only fictional fresh workspace. No scheduler, real campaign, model, external website or installed binary is exercised.",
        },
        "samples": samples, "sample_count": len(samples), "dom_observations": dom_observations,
        "summaries_ms": {name: {"passed_samples": len(values), "minimum": min(values),
            "median": round(statistics.median(values), 3), "maximum": max(values)} for name, values in grouped.items()},
        "checks": checks, "all_failures": failures, "page_errors": page_errors,
        "external_requests": external, "model_operations_requested": model_calls,
        "signals_received": signals, "resources": resources,
        "fictional_workspace_retained": str(workspace), "no_automatic_replay": True,
    })
    receipt["passed"] = (receipt["passed"] and not failures and not page_errors and not external
                         and model_calls == 0 and before == after and harness_before == harness_after
                         and all(resources.values()))
    exclusive_json(args.output_dir / "receipt.json", receipt)
    print(json.dumps({"receipt": str(args.output_dir / "receipt.json"), "passed": receipt["passed"],
                      "samples": len(samples), "failures": len(failures)}), flush=True)
    return 0 if receipt["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
