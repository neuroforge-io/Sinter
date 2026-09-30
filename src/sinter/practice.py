"""Bundled fictional practice data, independent of accounts and model services."""

from __future__ import annotations

import json
from importlib import resources

from . import campaigns, casebooks


def garden() -> dict:
    """Return fresh validated copies, keeping historical backup text intact."""
    assets = resources.files("sinter").joinpath("web")
    casebook = json.loads(
        assets.joinpath("offline-garden-casebook.json").read_text(encoding="utf-8")
    )
    campaign = json.loads(
        assets.joinpath("offline-garden-campaign.json").read_text(encoding="utf-8")
    )
    # Validation preserves evidence and historical answers. A shareable campaign
    # report intentionally holds some text and cannot substitute for import.
    return {
        "schema": "sinter-practice-bundle/v1",
        "id": "offline-garden",
        "fictional": True,
        "casebook": casebooks.validate(casebook),
        "campaign": campaigns.validate(campaign),
    }
