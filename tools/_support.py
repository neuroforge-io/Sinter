"""Shared command-line setup for optional development integrations."""
from __future__ import annotations

import argparse
import importlib
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from playwright.sync_api import Browser, Page, Playwright


CAMPAIGN_SAVED_MESSAGE = (
    "Campaign saved. Answers, costs, checks and actions will be here "
    "when you return."
)


def expect_campaign_message(page: Page, text: str, *, exact: bool = True) -> None:
    """Read the actual acknowledgement and await the unlocked campaign UI.

    Compact routine messages retain their original DOM, announce the full text,
    and expose a real message dialog. Older installed previews show the original
    inline message. Neither path substitutes an already-Saved status for the
    current acknowledgement. Save callers also await their actual HTTP response.
    """
    from playwright.sync_api import expect

    feedback = page.locator(".campaign-save-feedback")
    if exact:
        expect(feedback).to_have_text(text)
    else:
        expect(feedback).to_contain_text(text)
    expect(page.get_by_role("button", name="Save campaign", exact=True)).to_be_enabled()
    announcement = page.locator(".campaign-message-announcement")
    if announcement.count():
        expect(announcement).to_have_text(feedback.text_content())
        expect(page.get_by_role("button", name="Read full message", exact=True)).to_be_visible()
    else:
        expect(feedback).to_be_visible()


def save_campaign(page: Page) -> None:
    """Await this save's real reply, exact acknowledgement and completed unlock."""
    with page.expect_response("**/api/campaigns/save") as response:
        page.get_by_role("button", name="Save campaign", exact=True).click()
    assert response.value.status == 200, response.value.status
    expect_campaign_message(page, CAMPAIGN_SAVED_MESSAGE)


def require_module(
    parser: argparse.ArgumentParser, module: str, label: str, install: str
) -> None:
    """Fail with setup guidance when an optional tool cannot be imported."""
    try:
        importlib.import_module(module)
    except ImportError as exc:
        parser.error(
            f"{label} is required for this tool. From the repository root, run "
            f"`{install}` using this Python environment, then retry. "
            f"Import failed: {exc}"
        )


def browser_arguments(
    description: str, argv: Sequence[str] | None = None
) -> argparse.Namespace:
    """Handle help and dependency setup before any browser test side effects."""
    parser = argparse.ArgumentParser(
        description=description,
        epilog="Setup: python -m pip install '.[browser]' && "
        "python -m playwright install chromium. See docs/DEVELOPMENT.md.",
    )
    parser.add_argument(
        "--chromium",
        default=os.environ.get("SINTER_CHROMIUM"),
        metavar="PATH",
        help="Use an existing Chromium executable (default: SINTER_CHROMIUM).",
    )
    args = parser.parse_args(argv)
    require_module(
        parser, "playwright.sync_api", "Playwright",
        "python -m pip install '.[browser]'",
    )
    if args.chromium:
        executable = Path(args.chromium).expanduser().resolve()
        if not executable.is_file():
            parser.error(f"Chromium executable does not exist: {executable}")
        if not os.access(executable, os.X_OK):
            parser.error(f"Chromium path is not executable: {executable}")
        args.chromium = str(executable)
    return args


def launch_chromium(
    playwright: Playwright, executable_path: str | None = None
) -> Browser:
    """Start Chromium with actionable setup errors and a failing exit status."""
    from playwright.sync_api import Error

    try:
        return playwright.chromium.launch(
            headless=True, executable_path=executable_path
        )
    except Error as exc:
        raise SystemExit(
            f"{Path(sys.argv[0]).name}: error: Chromium could not start. "
            "Run `python -m playwright install --with-deps chromium`, or select "
            "an installed browser with --chromium PATH or SINTER_CHROMIUM.\n"
            f"{exc}"
        ) from None
