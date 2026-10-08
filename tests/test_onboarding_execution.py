"""Check module admission and failure retention without a Node command replay."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
import test_onboarding as harness


@pytest.mark.parametrize("returncode", [0, 9])
def test_explicit_module_fixture_keeps_source_graph_and_original_node_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, returncode: int
) -> None:
    """Admit unchanged modules once and never hide an actual command refusal."""
    root = Path(harness.__file__).resolve().parents[1]
    original = {
        path.relative_to(root / "src/sinter/web"): path.read_bytes()
        for path in (root / "src/sinter/web").rglob("*")
        if path.is_file()
    }
    entry = (root / "tests/onboarding.mjs").read_bytes()
    request = SimpleNamespace(node=SimpleNamespace(user_properties=[]))
    calls = []

    def run(
        command: list[str],
        *,
        cwd: Path,
        capture_output: bool,
        text: bool,
        encoding: str,
        timeout: int,
    ) -> SimpleNamespace:
        calls.append(command)
        assert command == ["inert-node", "--test", "tests/onboarding.mjs"]
        assert cwd == tmp_path and cwd != root
        assert capture_output is True and text is True
        assert encoding == "utf-8" and timeout == 20
        assert json.loads((cwd / "package.json").read_text()) == {"type": "module"}
        assert (cwd / "tests/onboarding.mjs").read_bytes() == entry
        copied = {
            path.relative_to(cwd / "src/sinter/web"): path.read_bytes()
            for path in (cwd / "src/sinter/web").rglob("*")
            if path.is_file()
        }
        assert copied == original
        return SimpleNamespace(
            returncode=returncode,
            stdout="inert retained stdout",
            stderr="inert Node option refusal" if returncode else "",
        )

    monkeypatch.setattr(harness.shutil, "which", lambda name: "inert-node")
    monkeypatch.setattr(harness.subprocess, "run", run)
    if returncode:
        with pytest.raises(AssertionError, match="inert Node option refusal"):
            harness.test_local_first_onboarding_controls(tmp_path, request)
    else:
        harness.test_local_first_onboarding_controls(tmp_path, request)
    assert len(calls) == 1
    name, raw = request.node.user_properties[0]
    assert name == "sinter_onboarding_node_diagnostics"
    assert json.loads(raw)["returncode"] == returncode
    assert json.loads(raw)["stdout"] == "inert retained stdout"
    assert (root / "tests/onboarding.mjs").read_bytes() == entry
