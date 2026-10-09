"""Profile driver-inclusive UI operations in a fresh fictional 170k-character portfolio.

Retains every attempted timing and failure outside Git. No timing thresholds: this is
a source-workflow measurement, not installed qualification or a hardware guarantee.
"""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import json
import platform
import statistics
import subprocess
import sys
import tempfile
import threading
import time
from collections import defaultdict
from contextlib import ExitStack
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "src")]

if TYPE_CHECKING:
    from playwright.sync_api import Page

from sinter import client  # noqa: E402
from tools._support import expect_campaign_message, save_campaign
from sinter.campaigns import validate  # noqa: E402
from sinter.server import make_server  # noqa: E402
from tools._support import browser_arguments, launch_chromium  # noqa: E402

ARTIFACTS: Path
TITLE = "Fictional 81-source operator-scale portfolio"
samples: list[dict] = []
errors: list[str] = []
external: list[str] = []
checks: list[str] = []
resources = {
    "browser_closed": False,
    "server_closed": False,
    "workspace_removed": False,
}


def digest(path: Path) -> str:
    """Hash bounded source or fictional evidence bytes."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def source_hashes() -> dict[str, str]:
    """Bind the entire UI plus the local campaign persistence implementation."""
    paths = list((ROOT / "src/sinter/web").glob("*"))
    paths += [
        ROOT / name
        for name in (
            "src/sinter/campaigns.py",
            "src/sinter/server.py",
            "src/sinter/workbench.py",
            "src/sinter/campaign_currency.py",
            "src/sinter/__init__.py",
            "tools/_support.py",
            "tools/campaign_portfolio_profile.py",
        )
    ]
    return {
        path.relative_to(ROOT).as_posix(): digest(path)
        for path in sorted(paths)
        if path.is_file()
    }


def character_count(value: object) -> int:
    """Count retained string values as Unicode code points, excluding object keys."""
    if isinstance(value, str):
        return len(value)
    if isinstance(value, list):
        return sum(character_count(item) for item in value)
    if isinstance(value, dict):
        return sum(character_count(item) for item in value.values())
    return 0


def text(length: int, marker: str) -> str:
    """Build plainly fictional wording at a specified code-point length."""
    sentence = (
        marker
        + " Fictional review only. No cash, owner, approval or IP right is confirmed. "
    )
    return (sentence * (length // len(sentence) + 1))[:length]


def fixture() -> dict:
    """Generate 81 sources, 27 products, 10 messages and exactly 170k characters."""
    routes = [
        {"name": f"Fictional route {index:02d}", "status": "clarification"}
        for index in range(1, 13)
    ]
    sources = [
        {
            "id": f"{index:032x}",
            "title": f"Fictional portfolio source {index:02d}",
            "url": f"https://example.invalid/source/{index:02d}",
            "checked_at": "2026-09-30",
            "notes": text(1150, f"Source {index:02d}."),
        }
        for index in range(1, 82)
    ]
    assets = [
        {
            "name": f"Fictional product {index:02d}",
            "kind": "product",
            "public_summary": text(1000, f"Product {index:02d}."),
            "differentiation_question": (
                "What measured comparison would support this fictional claim?"
            ),
            "funding_opportunities": [routes[index % 12]["name"]],
            "references": [
                {
                    "kind": "other",
                    "source_id": sources[index]["id"],
                    "title": sources[index]["title"],
                    "url": sources[index]["url"],
                    "checked_at": sources[index]["checked_at"],
                    "excerpt": sources[index]["notes"][:180],
                    "notes": "Fictional exact excerpt.",
                }
            ],
        }
        for index in range(27)
    ]
    messages = [
        {
            "subject": f"Fictional CommToken-{index:02d} record",
            "counterparty": "Fictional programme contact",
            "opportunity": routes[index % 12]["name"],
            "date": "" if index in (2, 8) else f"2026-09-{20 + index:02d}",
            "direction": "outgoing" if index in (2, 8) else "incoming",
            "status": "draft" if index in (2, 8) else "received",
            "channel": "email",
            "content": text(1400, f"Message {index:02d}."),
            "evidence_links": [
                {
                    "source_id": sources[index]["id"],
                    "title": sources[index]["title"],
                    "url": sources[index]["url"],
                    "checked_at": sources[index]["checked_at"],
                    "notes": "Fictional retained snapshot; do not infer a commitment.",
                }
            ],
        }
        for index in range(10)
    ]
    document = validate(
        {
            "title": TITLE,
            "organisation": "Fictional Community Association",
            "objective": "Compare fictional routes; cash and IP remain unresolved.",
            "opportunities": routes,
            "sources": sources,
            "assets": assets,
            "communications": messages,
            "actions": [
                {
                    "task": "Review a fictional quote",
                    "opportunity": routes[0]["name"],
                    "owner": "",
                    "due": "",
                    "status": "open",
                }
            ],
        }
    )
    remaining = 170000 - character_count(document)
    assert remaining >= 0
    for index, source in enumerate(document["sources"]):
        added = min(remaining, 6000 - len(source["notes"]))
        source["notes"] += text(added, f"Fictional capacity padding {index:02d}.")
        remaining -= added
        if not remaining:
            break
    assert remaining == 0
    document = validate(document)
    assert character_count(document) == 170000
    return document


def measured(name: str, index: int, action) -> None:
    """Retain every host wall-clock sample, including any failed attempt."""
    started = time.perf_counter_ns()
    sample = {"operation": name, "sample": index, "passed": False}
    try:
        action()
        sample["passed"] = True
    except Exception as error:
        sample["error"] = type(error).__name__ + ": " + str(error)[:1200]
        raise
    finally:
        sample["milliseconds"] = round((time.perf_counter_ns() - started) / 1e6, 3)
        samples.append(sample)
        print(json.dumps(sample), flush=True)


def ready(page: Page) -> None:
    """Wait for the actual saved campaign to open and unlock."""
    from playwright.sync_api import expect

    expect(page.get_by_label("Campaign name", exact=True)).to_have_value(TITLE)
    expect(page.get_by_role("button", name="Save campaign", exact=True)).to_be_enabled()
    expect(page.locator(".campaign-save-state")).to_have_text("Saved on this computer")


def save(page: Page) -> None:
    """Save and wait through the persisted campaign response and shelf refresh."""
    save_campaign(page)
    ready(page)


def indexes(page: Page) -> list[int]:
    """Read canonical row indices from currently visible DOM cards."""
    return page.locator(".campaign-communication:visible").evaluate_all(
        "cards => cards.map(card => Number(card.dataset.communicationIndex))"
    )


def guard(context, base: str) -> Page:
    """Refuse every external browser request and record JavaScript errors."""

    def route_request(route) -> None:
        if route.request.url.startswith(base + "/"):
            route.continue_()
        else:
            external.append(route.request.url)
            route.abort()

    context.route("**/*", route_request)
    page = context.new_page()
    page.set_default_timeout(10000)
    page.on("pageerror", lambda error: errors.append(str(error)))
    return page


def main(argv: list[str] | None = None) -> None:
    """Run bounded UI measurements, persist failure evidence and close resources."""
    global ARTIFACTS
    args = browser_arguments(__doc__, argv)
    from playwright.sync_api import expect, sync_playwright

    ARTIFACTS = Path(tempfile.mkdtemp(prefix="sinter-campaign-portfolio-profile-"))
    started_utc = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    hashes_before = source_hashes()
    document = fixture()
    fixture_path = ARTIFACTS / "fictional-portfolio.json"
    fixture_path.write_text(
        json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    receipt = {"passed": False}
    remote_calls = 0
    browser_version = "unknown"
    try:
        with tempfile.TemporaryDirectory(
            prefix="sinter-fictional-portfolio-workspace-"
        ) as workspace:
            with ExitStack() as stack:
                remote = stack.enter_context(
                    patch.object(
                        client,
                        "_open",
                        side_effect=AssertionError("No hosted operations admitted"),
                    )
                )
                server = make_server(port=0, directory=workspace)
                thread = threading.Thread(target=server.serve_forever, daemon=True)
                thread.start()
                base = f"http://127.0.0.1:{server.server_port}"
                try:
                    with sync_playwright() as driver:
                        browser = launch_chromium(driver, args.chromium)
                        browser_version = browser.version
                        try:
                            context = browser.new_context(
                                viewport={"width": 1440, "height": 1000}
                            )
                            page = guard(context, base)

                            def empty_open() -> None:
                                page.goto(base + "/#campaigns")
                                expect(
                                    page.locator(".campaign-save-bar")
                                ).to_be_visible()

                            measured("initial_empty_navigation", 1, empty_open)
                            for index in range(10):
                                measured(
                                    "driver_readonly_roundtrip",
                                    index + 1,
                                    lambda: page.evaluate("document.readyState"),
                                )
                            page.get_by_text(
                                "Import or back up a campaign", exact=True
                            ).click()

                            def import_backup() -> None:
                                page.get_by_label(
                                    "Import campaign backup", exact=True
                                ).set_input_files(fixture_path)
                                expect(
                                    page.get_by_label("Campaign name", exact=True)
                                ).to_have_value(TITLE)
                                expect_campaign_message(page, "Campaign imported locally.", exact=False)

                            measured("initial_import_backup", 1, import_backup)
                            measured("initial_save", 1, lambda: save(page))
                            saved_id = server.app.campaigns.list()[0]["id"]
                            before = server.app.campaigns.get(saved_id)
                            assert before["document"] == document
                            checks.append(
                                "Actual UI import and save preserve the complete "
                                "generated 170k-character portfolio."
                            )
                            for index in range(3):
                                fresh = browser.new_context(
                                    viewport={"width": 1440, "height": 1000}
                                )
                                fresh_page = guard(fresh, base)

                                def fresh_open() -> None:
                                    fresh_page.goto(base + "/#campaigns")
                                    ready(fresh_page)

                                measured(
                                    "saved_open_fresh_context", index + 1, fresh_open
                                )
                                fresh.close()
                            for index in range(5):

                                def reload_saved() -> None:
                                    page.reload()
                                    ready(page)

                                measured(
                                    "saved_open_warm_reload", index + 1, reload_saved
                                )
                            for index in range(5):
                                page.get_by_role(
                                    "tab", name="Opportunities", exact=True
                                ).click()

                                def communication_tab() -> None:
                                    page.get_by_role(
                                        "tab", name="Communications", exact=True
                                    ).click()
                                    expect(
                                        page.locator(".campaign-communication:visible")
                                    ).to_have_count(10)

                                measured(
                                    "communications_tab_render",
                                    index + 1,
                                    communication_tab,
                                )
                            search = page.get_by_label(
                                "Find a communication", exact=True
                            )
                            for index in range(5):
                                search.fill("")

                                def search_match() -> None:
                                    search.fill("CommToken-09")
                                    assert indexes(page) == [9]

                                measured(
                                    "communications_search_match",
                                    index + 1,
                                    search_match,
                                )

                                def no_match() -> None:
                                    search.fill("Fictional-no-record-matches-this")
                                    expect(
                                        page.locator(".campaign-communication:visible")
                                    ).to_have_count(0)

                                measured(
                                    "communications_search_no_match",
                                    index + 1,
                                    no_match,
                                )

                                def clear_match() -> None:
                                    page.get_by_role(
                                        "button",
                                        name="Clear communication filters",
                                        exact=True,
                                    ).click()
                                    expect(
                                        page.locator(".campaign-communication:visible")
                                    ).to_have_count(10)

                                measured(
                                    "communications_search_clear",
                                    index + 1,
                                    clear_match,
                                )
                            expected = copy.deepcopy(document)
                            for index in range(5):
                                row = page.locator(
                                    '.campaign-communication[data-communication-index="9"]'
                                )
                                details = row.locator("details").first
                                if details.get_attribute("open") is None:
                                    details.locator("summary").click()
                                evidence = row.get_by_role(
                                    "article", name="Communication evidence link"
                                )
                                picker = evidence.get_by_label(
                                    "Link to a saved campaign source", exact=True
                                )
                                chosen = document["sources"][
                                    80 if index % 2 == 0 else 79
                                ]
                                picker.fill("")
                                expect(
                                    evidence.locator(".campaign-source-matches button")
                                ).to_have_count(8)

                                def search_source() -> None:
                                    picker.fill(chosen["title"])
                                    expect(
                                        evidence.locator(
                                            ".campaign-source-matches button"
                                        )
                                    ).to_have_count(1)
                                    expect(
                                        evidence.get_by_role(
                                            "button",
                                            name="Link source: "
                                            + chosen["title"]
                                            + " · example.invalid",
                                            exact=True,
                                        )
                                    ).to_be_visible()

                                measured(
                                    "source_picker_search", index + 1, search_source
                                )

                                def select_source() -> None:
                                    evidence.locator(
                                        f'button[data-campaign-source-id="{chosen["id"]}"]'
                                    ).click()
                                    expect(
                                        evidence.get_by_label(
                                            "Evidence link", exact=True
                                        )
                                    ).to_have_value(chosen["url"])
                                    expect(
                                        page.locator(".campaign-save-state")
                                    ).to_have_text("Unsaved changes")

                                measured(
                                    "source_picker_explicit_select",
                                    index + 1,
                                    select_source,
                                )
                                expected["communications"][9]["evidence_links"][
                                    0
                                ].update(
                                    source_id=chosen["id"],
                                    title=chosen["title"],
                                    url=chosen["url"],
                                    checked_at=chosen["checked_at"],
                                )
                                measured(
                                    "modified_portfolio_save",
                                    index + 1,
                                    lambda: save(page),
                                )
                                after = server.app.campaigns.get(saved_id)
                                assert after["document"] == expected

                                def reopen_selected() -> None:
                                    page.reload()
                                    ready(page)
                                    page.get_by_role(
                                        "tab", name="Communications", exact=True
                                    ).click()
                                    last = page.locator(
                                        '.campaign-communication[data-communication-index="9"]'
                                    )
                                    last.locator("summary").first.click()
                                    expect(
                                        last.get_by_label("Evidence link", exact=True)
                                    ).to_have_value(chosen["url"])

                                measured(
                                    "saved_reopen_and_exact_link",
                                    index + 1,
                                    reopen_selected,
                                )
                            checks.append(
                                "View-only searches preserve canonical records; five "
                                "explicit links persist only the selected "
                                "evidence snapshot."
                            )
                            assert (
                                server.app.campaigns.get(saved_id)["document"]
                                == expected
                            )
                            page.get_by_label(
                                "Communication order", exact=True
                            ).select_option("newest")
                            assert indexes(page) == [9, 7, 6, 5, 4, 3, 1, 0, 2, 8]
                            assert (
                                server.app.campaigns.get(saved_id)["document"]
                                == expected
                            )
                            checks.append(
                                "Chronology retains undated drafts last and original "
                                "canonical indices."
                            )
                            page.screenshot(
                                path=str(ARTIFACTS / "communications-at-scale.png")
                            )
                            page.get_by_role(
                                "tab", name="Products & IP", exact=True
                            ).click()
                            expect(
                                page.get_by_label("Find a product or asset", exact=True)
                            ).to_be_visible()
                            page.screenshot(
                                path=str(ARTIFACTS / "products-at-scale.png")
                            )
                            assert not errors and not external
                            remote.assert_not_called()
                            receipt["passed"] = True
                        finally:
                            browser.close()
                            resources["browser_closed"] = True
                finally:
                    remote_calls = remote.call_count
                    server.shutdown()
                    server.app.close()
                    server.server_close()
                    thread.join(timeout=5)
                    resources["server_closed"] = not thread.is_alive()
        resources["workspace_removed"] = not Path(workspace).exists()
    except (Exception, SystemExit) as error:
        receipt["failure"] = type(error).__name__ + ": " + str(error)[:2000]
        if "workspace" in locals():
            resources["workspace_removed"] = not Path(workspace).exists()
    grouped: dict[str, list[float]] = defaultdict(list)
    for sample in samples:
        if sample["passed"]:
            grouped[sample["operation"]].append(sample["milliseconds"])
    after_hashes = source_hashes()
    unchanged = hashes_before == after_hashes
    receipt.update(
        {
            "schema": "sinter-fictional-portfolio-ui-benchmark/v1",
            "probe_sha256": digest(Path(__file__).resolve()),
            "fixture_only": True,
            "started_utc": started_utc,
            "browser": {
                "executable": args.chromium or "Playwright configured Chromium",
                "version": browser_version,
                "headless": True,
                "viewport": {"width": 1440, "height": 1000},
            },
            "python": sys.version.split()[0],
            "playwright": importlib.metadata.version("playwright"),
            "platform": platform.platform(),
            "source_commit": subprocess.check_output(
                ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
            ).strip(),
            "source_sha256": hashes_before,
            "source_sha256_after": after_hashes,
            "source_unchanged_during_run": unchanged,
            "fixture": {
                "sources": 81,
                "products": 27,
                "communications": 10,
                "routes": 12,
                "normalized_string_code_points": character_count(document),
                "json_bytes": fixture_path.stat().st_size,
                "sha256": digest(fixture_path),
            },
            "methodology": {
                "timer": (
                    "Host perf_counter_ns before first UI operation through stated "
                    "DOM assertion/unlock; includes Playwright IPC, auto-scroll, "
                    "actionability waits and assertions."
                ),
                "fresh_context": (
                    "New browser context/page with empty cookies/cache; same "
                    "already-running Chrome/server, warm OS filesystem. "
                    "Not native cold startup."
                ),
                "warm": (
                    "Same context and localhost server. No CPU/network throttling; "
                    "5 samples per repeated action. No discarded warmups or outliers."
                ),
                "overhead": (
                    "10 readonly document.readyState roundtrips measured "
                    "separately; not subtracted."
                ),
                "scope": (
                    "Fictional fresh SQLite workspace; no direct JS page-state "
                    "edits, model, external website, private campaign, installed "
                    "binary or representative hardware claim."
                ),
            },
            "samples": samples,
            "sample_count": len(samples),
            "summaries_ms": {
                name: {
                    "passed_samples": len(values),
                    "minimum": min(values),
                    "median": round(statistics.median(values), 3),
                    "maximum": max(values),
                }
                for name, values in grouped.items()
            },
            "checks": checks,
            "browser_errors": errors,
            "external_requests": external,
            "model_operations_requested": remote_calls,
            "resources": resources,
        }
    )
    receipt["passed"] = receipt["passed"] and unchanged and all(resources.values())
    (ARTIFACTS / "receipt.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    for retained in ARTIFACTS.iterdir():
        if retained.is_file():
            retained.chmod(0o600)
    print(
        json.dumps(
            {
                "receipt": str(ARTIFACTS / "receipt.json"),
                "passed": receipt["passed"],
                "samples": len(samples),
            }
        )
    )
    if not receipt["passed"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
