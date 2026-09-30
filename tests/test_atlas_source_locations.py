"""Bound producer locations without inventing omitted identities or coordinates."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pytest

from sinter import atlas, client

FIXTURES = Path(__file__).parent / "fixtures"


def bundle():
    return json.loads((FIXTURES / "rkc_markdown_bundle.v1.json").read_text())


def packet():
    return json.loads((FIXTURES / "rkc_sinter_context_bridge.v1.json").read_text())[
        "packets"
    ]["before"]


@pytest.fixture(autouse=True)
def no_external_operations(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail(
            "Source-location checks must not contact models or read credentials"
        )

    for name in ("chat", "search", "_load_key", "destination_key"):
        monkeypatch.setattr(client, name, blocked)
    monkeypatch.setattr(atlas.urllib.request, "build_opener", blocked)


@pytest.mark.parametrize("with_sections", [False, True])
def test_node_artifact_binds_path_even_when_source_omits_artifact_id(with_sections):
    document = bundle()
    node = document["nodes"][0]
    node["source"].pop("artifact_id")
    node["source"]["path"] = "contradictory.md"
    if with_sections:
        source_document = document["documents"][0]
        source_document["path"] = "contradictory.md"
        source_document["attributes"].pop("artifact_id")
    else:
        document.pop("documents")
    original = copy.deepcopy(document)
    assert node["artifact_id"] == document["artifacts"][0]["id"]
    assert document["artifacts"][0]["path"] == "handbook.md"
    with pytest.raises(ValueError, match="artifact|path"):
        atlas.validate(document)
    assert document == original


def test_known_node_binding_checks_omitted_source_id_without_inserting_it():
    document = bundle()
    source = document["nodes"][0]["source"]
    source.pop("artifact_id")
    original = copy.deepcopy(document)
    retained = atlas.context(document, "renewals")["items"][0]
    assert retained["source"] == source
    assert "artifact_id" not in retained["source"]
    assert retained["text"] == document["documents"][0]["sections"][0]["markdown"]
    assert document == original


def test_source_id_can_bind_without_a_node_artifact_id():
    document = bundle()
    document["nodes"][0].pop("artifact_id")
    original = copy.deepcopy(document)
    assert (
        atlas.context(document, "renewals")["items"][0]["source"]
        == (document["nodes"][0]["source"])
    )
    assert document == original


@pytest.mark.parametrize("kind", ["context", "bundle"])
@pytest.mark.parametrize("omitted", ["start_column", "end_column", "both"])
def test_partial_same_line_columns_are_retained_without_inferred_endpoints(
    kind, omitted
):
    document = packet() if kind == "context" else bundle()
    node = (
        next(row for row in document["items"] if "source" in row)
        if kind == "context"
        else document["nodes"][0]
    )
    source = node["source"]
    source.update(start_line=5, end_line=5, start_column=7, end_column=2)
    for key in ("start_column", "end_column") if omitted == "both" else (omitted,):
        source.pop(key)
    if kind == "bundle":
        document["documents"][0]["sections"][0]["attributes"].update(
            start_line=5, end_line=5
        )
    original = copy.deepcopy(document)
    retained = atlas.validate(document)["items"]
    expected = next(row for row in retained if row.get("source") == source)
    assert expected["source"] == source
    assert document == original
    assert all(
        key in source or key not in expected["source"]
        for key in ("start_column", "end_column")
    )


@pytest.mark.parametrize("end_column", [0, 6])
def test_explicit_reversed_columns_on_known_same_line_are_still_rejected(end_column):
    document = packet()
    row = next(row for row in document["items"] if "source" in row)
    row["source"].update(
        start_line=5, end_line=5, start_column=7, end_column=end_column
    )
    original = copy.deepcopy(document)
    with pytest.raises(ValueError, match="column range is reversed"):
        atlas.validate(document)
    assert document == original


@pytest.mark.parametrize("lines", [(5, 6), (0, 0)])
def test_columns_are_not_ordered_across_distinct_or_unknown_lines(lines):
    document = packet()
    source = next(row for row in document["items"] if "source" in row)["source"]
    source.update(start_line=lines[0], end_line=lines[1], start_column=7, end_column=2)
    assert any(row.get("source") == source for row in atlas.validate(document)["items"])


def test_absent_source_object_is_not_created_from_known_node_artifact():
    document = bundle()
    document["nodes"][0].pop("source")
    retained = atlas.context(document, "renewals")["items"][0]
    assert retained["path"] == "handbook.md"
    assert "source" not in retained
    assert retained["text"] == document["documents"][0]["sections"][0]["markdown"]
