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
    from playwright.sync_api import Browser, Playwright


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
