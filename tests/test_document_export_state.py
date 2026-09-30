"""Exercise document recovery and explicit local choices in CI."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("suite", [
    "document_export_state.mjs", "casebook_handover.mjs",
    "report_drafts.mjs", "campaign_source_options.mjs",
])
def test_document_export_state(suite):
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to exercise browser-side document state")
    root = Path(__file__).resolve().parents[1]
    result = subprocess.run(
        [node, "--test", str(root / "tests" / suite)],
        cwd=root,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
