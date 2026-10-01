"""Human outputs retain the same fictional source packet as structured output."""

from __future__ import annotations

import copy

import pytest

from sinter import native_window, runtime_cli
from sinter.presentation import result_markdown


@pytest.mark.parametrize("complete", [True, False])
def test_human_answer_retains_exact_sources_and_incomplete_status(complete):
    value = {
        "complete": complete,
        "results": [
            {"step": "Answer", "content": "Fictional loans last 14 days [e1]."}
        ],
        "sources": [
            {
                "sources": [{"id": "source-1", "title": "Fictional handbook.md"}],
                "excerpts": [
                    {
                        "id": "e1",
                        "source_id": "source-1",
                        "location": "lines 1–2",
                        "quote": "Fictional loans last 14 days.",
                    }
                ],
            }
        ],
    }
    original = copy.deepcopy(value)
    rendered = runtime_cli._human(value)
    assert rendered == native_window.result_markdown(value) == result_markdown(value)
    assert "UNVERIFIED MODEL DRAFT" in rendered
    assert "Fictional handbook.md" in rendered and '"source_id": "source-1"' in rendered
    assert "Fictional loans last 14 days." in rendered and "lines 1–2" in rendered
    assert ("INCOMPLETE:" in rendered) is (not complete)
    assert value == original


def test_shared_readable_source_report_and_partial_output_are_preserved():
    assert result_markdown({"markdown": "# Fictional source report"}) == (
        "# Fictional source report"
    )
    partial = result_markdown({"partial": {"content": "Fictional interrupted draft"}})
    assert "INCOMPLETE:" in partial and "Fictional interrupted draft" in partial
