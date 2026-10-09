"""Keep the fictional comparison harness bounded and safe before browser startup."""

from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from sinter.campaigns import validate

ROOT = Path(__file__).resolve().parents[1]
TOOL = ROOT / "tools" / "campaign_communications_profile.py"
NEW_WEB_MODULES = (
    "src/sinter/web/campaign-communications.js",
    "src/sinter/web/campaign-requirement-policy.js",
)


@pytest.fixture(scope="module")
def profile():
    """Load the standard-library-only harness without starting a browser."""
    specification = importlib.util.spec_from_file_location(
        "sinter_communications_profile_tests", TOOL
    )
    assert specification is not None and specification.loader is not None
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def run_cli(arguments: list[str], directory: Path) -> subprocess.CompletedProcess:
    """Remove site packages so CLI admission cannot depend on Playwright."""
    return subprocess.run(
        [sys.executable, "-I", "-S", str(TOOL), *arguments],
        cwd=directory,
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )


def test_help_without_playwright_or_output_artifacts(tmp_path):
    result = run_cli(["--help"], tmp_path)
    assert result.returncode == 0, result.stderr
    assert "usage:" in result.stdout
    assert "--source-root" in result.stdout
    assert "--output-dir" in result.stdout
    assert "Traceback" not in result.stderr
    assert not list(tmp_path.iterdir())


def test_existing_output_directory_is_retained_without_modification(tmp_path):
    output = tmp_path / "earlier-evidence"
    output.mkdir()
    nested = output / "nested"
    nested.mkdir()
    (output / "receipt.json").write_bytes(b'{"historical":true}\n')
    (nested / "original.bin").write_bytes(b"\x00original\xff\n")

    def inventory():
        return {
            str(path.relative_to(tmp_path)): (
                path.stat().st_mode,
                path.read_bytes() if path.is_file() else None,
            )
            for path in tmp_path.rglob("*")
        }

    before = inventory()
    result = run_cli(
        ["--source-root", str(ROOT), "--output-dir", str(output)], tmp_path
    )
    assert result.returncode == 2
    assert "already exists; retain it and choose a new directory" in result.stderr
    assert "Traceback" not in result.stderr
    assert inventory() == before
    assert not (output / "started.json").exists()
    assert not (output / "fictional-workspace").exists()


def test_comparison_fixture_is_valid_deterministic_and_exactly_bounded(profile):
    first = profile.fixture(validate)
    second = profile.fixture(validate)
    assert first == second == validate(first)
    assert profile.encoded(first) == profile.encoded(second)
    assert profile.character_count(first) == 170_000
    assert len(first["communications"]) == 47
    assert len(first["sources"]) == 76
    assert len(first["opportunities"]) == 12
    assert len(profile.encoded(first)) < 1_000_000
    assert "🐝" in first["communications"][0]["content"]
    assert "e\u0301" in first["communications"][0]["content"]
    assert {row["status"] for row in first["communications"]} == {
        "draft", "sent", "received"
    }
    source_ids = {row["id"] for row in first["sources"]}
    for row in first["communications"]:
        assert row["direction"] == (
            "incoming" if row["status"] == "received" else "outgoing"
        )
        assert row["evidence_links"][0]["source_id"] in source_ids
        if row["status"] == "draft":
            assert row["date"] == ""


def test_runtime_source_pins_include_both_extracted_web_modules(profile):
    pinned = profile.source_hashes(ROOT)
    for name in NEW_WEB_MODULES:
        original = (ROOT / name).read_bytes()
        assert pinned[name] == {
            "bytes": len(original),
            "sha256": hashlib.sha256(original).hexdigest(),
        }


def test_runtime_module_drift_changes_the_before_after_pins(profile, tmp_path):
    for name in NEW_WEB_MODULES:
        target = tmp_path / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"// fictional original module\n")
    original = profile.source_hashes(tmp_path)
    for name in NEW_WEB_MODULES:
        (tmp_path / name).write_bytes(b"// fictional changed module\n")
        changed = profile.source_hashes(tmp_path)
        assert changed != original
        assert changed[name]["sha256"] != original[name]["sha256"]
