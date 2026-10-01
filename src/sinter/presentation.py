"""Readable shared results without losing sources or implying model validation."""

from __future__ import annotations

import json


def result_markdown(value: dict) -> str:
    """Render source reports and model runs for both native and human CLI use."""
    if isinstance(value.get("markdown"), str):
        return value["markdown"]
    sections = ["# UNVERIFIED MODEL DRAFT — CHECK THE ORIGINAL EXCERPT"]
    if value.get("complete") is not True:
        sections.append("INCOMPLETE: do not treat this as a finished answer.")
    for row in value.get("results", []):
        sections.append("## " + str(row.get("step", "Answer")))
        sections.append(str(row.get("content", "")))
    partial = value.get("partial")
    if isinstance(partial, dict):
        sections.extend(["## Incomplete output", str(partial.get("content", ""))])
    sections.append("## Exact source material and provenance")
    sections.append(json.dumps(value.get("sources", []), ensure_ascii=False, indent=2))
    return "\n\n".join(sections)
