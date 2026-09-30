"""Installed resources expose the agreed example without inferring new facts."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import zipfile
from importlib import resources
from pathlib import Path
from unittest.mock import patch

from sinter import client, practice
from tools.build_zipapp import build

ROOT = Path(__file__).resolve().parents[1]


def test_bundled_practice_is_exactly_the_agreed_fictional_data():
    assets = resources.files("sinter").joinpath("web")
    for name in ("casebook", "campaign"):
        assert (
            assets.joinpath(f"offline-garden-{name}.json").read_bytes()
            == (ROOT / "examples/offline-garden" / f"{name}.json").read_bytes()
        )


def test_practice_copies_retain_unknowns_and_historical_text():
    with patch.object(client, "_open", side_effect=AssertionError("Offline only")):
        bundle = practice.garden()
        original = practice.garden()
    assert bundle["fictional"] is True
    assert bundle["casebook"]["document_type"] == "handover"
    assert len(bundle["casebook"]["documents"]) == 4
    assert len(bundle["campaign"]["opportunities"]) == 2
    assert len(bundle["campaign"]["actions"]) == 4
    assert bundle["campaign"]["budget"][0]["unit_cost"] is None
    assert "Not submitted." in bundle["campaign"]["answers"][0]["text"]
    assert not any(row["owner_confirmed"] for row in bundle["campaign"]["actions"])
    bundle["casebook"]["documents"][0]["content"] = "Local practice edit"
    bundle["campaign"]["actions"][0]["owner"] = "Fictional editor"
    assert practice.garden() == original


def test_portable_practice_loads_outside_the_repository(tmp_path):
    archive = build(tmp_path / "practice.pyz")
    with zipfile.ZipFile(archive) as package:
        assert "sinter/web/offline-garden-casebook.json" in package.namelist()
        assert "sinter/web/offline-garden-campaign.json" in package.namelist()
    environment = dict(os.environ)
    environment.pop("PYTHONPATH", None)
    result = subprocess.run(
        [
            sys.executable,
            "-I",
            "-c",
            "import sys,json; "
            "sys.path.insert(0,sys.argv[1]); from sinter.practice import garden; "
            "print(json.dumps(garden()))",
            str(archive),
        ],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )
    assert json.loads(result.stdout) == practice.garden()
