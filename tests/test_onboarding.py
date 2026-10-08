"""Check actionable first-use guidance without apps, accounts or providers."""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest


def test_local_first_onboarding_controls(
    tmp_path: Path, request: pytest.FixtureRequest
) -> None:
    """Click the rendered entry controls and retain original practice evidence."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node is required to exercise first-use controls.")
    root = Path(__file__).resolve().parents[1]
    # Use Node's explicit package boundary for unchanged source copies. This
    # keeps .js imports unambiguous without a version-specific experimental flag.
    shutil.copytree(root / "src/sinter/web", tmp_path / "src/sinter/web")
    (tmp_path / "tests").mkdir()
    shutil.copyfile(root / "tests/onboarding.mjs", tmp_path / "tests/onboarding.mjs")
    (tmp_path / "package.json").write_text('{"type":"module"}\n', encoding="utf-8")
    command = [node, "--test", "tests/onboarding.mjs"]
    result = subprocess.run(
        command,
        cwd=tmp_path,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=20,
    )
    request.node.user_properties.append(
        (
            "sinter_onboarding_node_diagnostics",
            json.dumps(
                {
                    "command": command,
                    "cwd": str(tmp_path),
                    "module_type": "module",
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
                sort_keys=True,
            ),
        )
    )
    assert result.returncode == 0, result.stdout + result.stderr
