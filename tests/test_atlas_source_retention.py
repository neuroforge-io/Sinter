"""Source inspection and explicit updates using wholly fictional RKC records."""

import copy
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

import pytest

from sinter import atlas, client

FIXTURES = Path(__file__).parent / "fixtures"


def bridge():
    return json.loads((FIXTURES / "rkc_sinter_context_bridge.v1.json").read_text())


def bundle():
    return json.loads((FIXTURES / "rkc_markdown_bundle.v1.json").read_text())


def source_packet():
    packet = bridge()["packets"]["before"]
    row = next(item for item in packet["items"] if item["object_type"] == "artifact")
    row["source"].update(
        start_byte=0,
        end_byte=236,
        start_line=1,
        end_line=13,
        start_column=0,
        end_column=0,
        anchor="lantern-library-handbook",
    )
    return packet


@pytest.fixture(autouse=True)
def no_inference_or_credentials(monkeypatch):
    def blocked(*args, **kwargs):
        pytest.fail("Model, search, credentials and external retrieval are forbidden")

    for name in ("chat", "search", "_load_key", "destination_key"):
        monkeypatch.setattr(client, name, blocked)
    monkeypatch.setattr(atlas.urllib.request, "build_opener", blocked)


def test_supplied_context_source_survives_selection_and_json_export():
    packet = source_packet()
    original = copy.deepcopy(packet)
    expected = next(row for row in packet["items"] if "source" in row)["source"]
    result = atlas.context(packet, "Lantern lending period")
    retained = next(row for row in result["items"] if row["object_type"] == "artifact")
    assert retained["source"] == expected
    assert json.loads(json.dumps(result))["items"] == result["items"]
    assert retained["start"] == 0 and retained["end"] == len(retained["text"])
    assert "Source object location" in result["markdown"]
    assert "not excerpt offsets" in result["markdown"]
    retained["source"]["path"] = "changed-only-in-working-view.md"
    assert packet == original


@pytest.mark.parametrize("value", [None, "missing"])
def test_missing_context_source_does_not_invent_a_location(value):
    packet = bridge()["packets"]["before"]
    for row in packet["items"]:
        if value is None:
            row["source"] = None
        else:
            row.pop("source", None)
    assert all("source" not in row for row in atlas.validate(packet)["items"])


@pytest.mark.parametrize(
    "change",
    [
        {"start_byte": True},
        {"start_line": -1},
        {"end_column": 1.5},
        {"start_column": "0"},
        {"start_byte": 10, "end_byte": 9},
        {"start_line": 5, "end_line": 4},
        {"start_line": 5, "end_line": 5, "start_column": 7, "end_column": 6},
        {"anchor": []},
        {"path": []},
        {"unsupported_location": 1},
        {"path": "a-different-artifact.md"},
    ],
)
def test_invalid_or_conflicting_context_source_is_rejected(change):
    packet = source_packet()
    row = next(item for item in packet["items"] if "source" in item)
    row["source"].update(change)
    with pytest.raises(ValueError):
        atlas.validate(packet)


@pytest.mark.parametrize("value", [[], "not a location", 12])
def test_nonobject_source_is_rejected(value):
    packet = source_packet()
    packet["items"][0]["source"] = value
    with pytest.raises(ValueError):
        atlas.validate(packet)


def test_omitted_or_zero_coordinates_are_not_fabricated():
    packet = bridge()["packets"]["before"]
    expected = next(row for row in packet["items"] if "source" in row)["source"]
    row = next(
        row
        for row in atlas.validate(packet)["items"]
        if row["object_type"] == "artifact"
    )
    assert row["source"] == expected
    assert not any(key in row["source"] for key in ("start_line", "start_byte"))
    packet = source_packet()
    supplied = next(row for row in packet["items"] if "source" in row)["source"]
    supplied.update(
        start_byte=0, end_byte=0, start_line=0, end_line=0, start_column=0, end_column=0
    )
    retained = next(
        row
        for row in atlas.validate(packet)["items"]
        if row["object_type"] == "artifact"
    )
    assert retained["source"] == supplied


def test_source_paths_and_anchors_are_inert_labels():
    packet = source_packet()
    row = next(item for item in packet["items"] if "source" in item)
    label = "javascript:fictional() <script>fictional()</script>"
    row["path"] = row["source"]["path"] = label
    row["source"]["anchor"] = label
    with patch.object(
        atlas, "Path", side_effect=AssertionError("No path may be opened")
    ):
        result = atlas.context(packet, "Lantern")
    assert (
        next(item for item in result["items"] if "source" in item)["source"]["path"]
        == label
    )
    assert "<script>" not in result["markdown"]


def test_markdown_body_is_searchable_with_existing_node_identity_and_source():
    document = bundle()
    original = copy.deepcopy(document)
    node = document["nodes"][0]
    section = document["documents"][0]["sections"][0]
    result = atlas.context(document, "renewals")
    assert len(result["items"]) == 1, "Only section body contains the search term"
    row = result["items"][0]
    assert row["text"] == section["markdown"]
    assert row["pointer"] == "/documents/0/sections/0/markdown"
    expected = hashlib.sha256(
        (document["snapshot"]["id"] + "\0node\0" + node["id"]).encode()
    ).hexdigest()
    assert row["id"] == expected and row["object_id"] == node["id"]
    assert row["object_type"] == "node"
    assert row["source"] == node["source"]
    assert row["evidence_ids"] == section["evidence_ids"]
    assert row["document_id"] == document["documents"][0]["id"]
    assert row["section_id"] == section["id"]
    assert row["document_kind"] == "source_document"
    assert row["generator"] == "rkc.markdown"
    assert row["document_status"] == "validated"
    assert document == original


def test_plain_text_fallback_identifies_the_actual_retained_field():
    document = bundle()
    section = document["documents"][0]["sections"][0]
    section["markdown"] = ""
    section["plain_text"] = "Wholly fictional renewals need approval."
    result = atlas.context(document, "renewals")
    assert result["items"][0]["text"] == section["plain_text"]
    assert result["items"][0]["pointer"] == "/documents/0/sections/0/plain_text"


def test_unbound_or_generated_sections_do_not_replace_source_nodes():
    for change in ("unbound", "generated"):
        document = bundle()
        if change == "unbound":
            document["documents"][0]["sections"][0]["id"] = "not-an-existing-node"
        else:
            document["documents"][0]["kind"] = "architecture"
        view = atlas.validate(document)
        assert len(view["items"]) == 1
        assert view["items"][0]["text"] == document["nodes"][0]["name"]
        assert not atlas.context(document, "renewals")["items"]
        assert any("not complete source files" in value for value in view["warnings"])


@pytest.mark.parametrize("optional", ["documents", "sections"])
def test_nil_optional_markdown_collections_keep_existing_node_view(optional):
    document = bundle()
    if optional == "documents":
        document["documents"] = None
    else:
        document["documents"][0]["sections"] = None
    view = atlas.validate(document)
    assert view["items"][0]["text"] == document["nodes"][0]["name"]


@pytest.mark.parametrize(
    "conflict",
    [
        "path",
        "artifact",
        "anchor",
        "start_line",
        "end_line",
        "document_id",
        "section_id",
        "ambiguous_body",
        "missing_evidence",
        "artifact_duplicate",
    ],
)
def test_conflicting_section_binding_is_rejected(conflict):
    document = bundle()
    row = document["documents"][0]
    section = row["sections"][0]
    if conflict == "path":
        row["path"] = "different.md"
    elif conflict == "artifact":
        row["attributes"]["artifact_id"] = "different-artifact"
    elif conflict in {"anchor", "start_line", "end_line"}:
        section["attributes"][conflict] = (
            "different-anchor" if conflict == "anchor" else 99
        )
    elif conflict == "document_id":
        document["documents"].append(copy.deepcopy(row))
    elif conflict == "section_id":
        row["sections"].append(copy.deepcopy(section))
    elif conflict == "ambiguous_body":
        second = copy.deepcopy(row)
        second["id"] = "a-second-document"
        second["sections"][0]["markdown"] = "Conflicting fictional body"
        document["documents"].append(second)
    elif conflict == "missing_evidence":
        section["evidence_ids"] = ["an-unsupplied-evidence-object"]
    else:
        document["artifacts"].append(
            {**document["artifacts"][0], "path": "different.md"}
        )
    with pytest.raises(ValueError):
        atlas.validate(document)


def test_truncation_preserves_body_location_and_explicit_character_offsets():
    document = bundle()
    body = "Wholly fictional renewals. " * 150
    document["documents"][0]["sections"][0]["markdown"] = body
    result = atlas.context(document, "renewals")
    row = result["items"][0]
    assert row["text"] == body[:3000] and row["excerpt_truncated"] is True
    assert row["start"] == 0 and row["end"] == 3000
    assert row["source"] == document["nodes"][0]["source"]


def test_explicit_new_snapshot_changes_citations_without_mutating_retained_packet():
    packets = bridge()["packets"]
    before = copy.deepcopy(packets["before"])
    original = copy.deepcopy(before)
    old = atlas.context(before, "Lantern lending period")
    updated = atlas.context(packets["after"], "Lantern lending period")
    retained = atlas.context(packets["old_retained"], "Lantern lending period")
    assert before == original
    assert old["snapshot_id"] == retained["snapshot_id"] != updated["snapshot_id"]
    assert {row["id"] for row in old["items"]}.isdisjoint(
        {row["id"] for row in updated["items"]}
    )
    assert all("14 days" in row["text"] for row in old["items"])
    assert all("21 days" in row["text"] for row in updated["items"])
    assert [(row["id"], row["text"]) for row in old["items"]] == [
        (row["id"], row["text"]) for row in retained["items"]
    ]
    swapped = copy.deepcopy(before)
    swapped["snapshot_id"] = updated["snapshot_id"]
    with pytest.raises(ValueError, match="citation"):
        atlas.validate(swapped)


@pytest.mark.parametrize(
    "field", ["documents", "sections", "attributes", "section_attributes", "ordinal"]
)
def test_malformed_new_bundle_fields_are_rejected(field):
    document = bundle()
    row = document["documents"][0]
    section = row["sections"][0]
    if field == "documents":
        document[field] = {}
    elif field == "sections":
        row[field] = {}
    elif field == "attributes":
        row[field] = []
    elif field == "section_attributes":
        section["attributes"] = []
    else:
        section[field] = True
    with pytest.raises(ValueError):
        atlas.validate(document)


def test_markdown_body_obeys_existing_indexed_text_bound():
    document = bundle()
    document["documents"][0]["sections"][0]["markdown"] = "x" * 262145
    with pytest.raises(ValueError, match="characters"):
        atlas.validate(document)


def test_context_artifact_source_cannot_claim_a_different_artifact_identity():
    document = source_packet()
    row = next(item for item in document["items"] if item["object_type"] == "artifact")
    row["source"]["artifact_id"] = "a-different-artifact"
    with pytest.raises(ValueError, match="artifact"):
        atlas.validate(document)


def test_source_can_omit_artifact_id_without_inventing_it():
    document = source_packet()
    row = next(item for item in document["items"] if item["object_type"] == "artifact")
    row["source"].pop("artifact_id")
    retained = next(
        item
        for item in atlas.validate(document)["items"]
        if item["object_type"] == "artifact"
    )
    assert retained["source"] == row["source"]
    assert "artifact_id" not in retained["source"]


def test_missing_node_artifact_is_rejected_even_if_source_omits_id():
    document = bundle()
    document["nodes"][0]["artifact_id"] = "a-missing-artifact"
    document["nodes"][0]["source"].pop("artifact_id")
    with pytest.raises(ValueError, match="artifact"):
        atlas.validate(document)


def test_duplicate_bundle_evidence_cannot_supply_an_ambiguous_binding():
    document = bundle()
    second = copy.deepcopy(document["evidence"][0])
    second["source"]["start_line"] = 999
    document["evidence"].append(second)
    with pytest.raises(ValueError, match="Duplicate evidence"):
        atlas.validate(document)


@pytest.mark.parametrize("node_kind", ["document_section", "symbol"])
@pytest.mark.parametrize("source_id", ["omitted", "empty", "present"])
@pytest.mark.parametrize("document_id", ["omitted", "empty", "present"])
def test_known_node_artifact_path_rejects_contradictory_optional_source(
    node_kind, source_id, document_id
):
    document = bundle()
    node = document["nodes"][0]
    node["kind"] = node_kind
    if source_id == "omitted":
        node["source"].pop("artifact_id")
    elif source_id == "empty":
        node["source"]["artifact_id"] = ""
    node["source"]["path"] = "fictional-other-book.md"
    document["documents"][0]["path"] = "fictional-other-book.md"
    if document_id == "omitted":
        document["documents"][0]["attributes"].pop("artifact_id")
    elif document_id == "empty":
        document["documents"][0]["attributes"]["artifact_id"] = ""
    original = copy.deepcopy(document)
    with pytest.raises(ValueError, match="path"):
        atlas.validate(document)
    with pytest.raises(ValueError, match="path"):
        atlas.context(document, "renewals")
    assert document == original


@pytest.mark.parametrize("omission", ["documents", "document_path", "node_artifact"])
def test_known_artifact_path_is_checked_without_document_or_node_metadata(omission):
    document = bundle()
    node = document["nodes"][0]
    node["source"]["path"] = "fictional-other-book.md"
    if omission == "node_artifact":
        node.pop("artifact_id")
    else:
        node["source"].pop("artifact_id")
    if omission == "documents":
        document.pop("documents")
    else:
        document["documents"][0].pop("path")
    with pytest.raises(ValueError, match="path"):
        atlas.validate(document)


@pytest.mark.parametrize("omit", ["source_artifact", "document_artifact", "both"])
def test_consistent_optional_artifact_metadata_remains_supported(omit):
    document = bundle()
    node = document["nodes"][0]
    if omit in {"source_artifact", "both"}:
        node["source"].pop("artifact_id")
    if omit in {"document_artifact", "both"}:
        document["documents"][0]["attributes"].pop("artifact_id")
    result = atlas.context(document, "renewals")
    assert (
        result["items"][0]["text"]
        == document["documents"][0]["sections"][0]["markdown"]
    )
    assert result["items"][0]["source"] == node["source"]


@pytest.mark.parametrize("binding", ["no_artifact_identity", "unknown_artifact_path"])
def test_unavailable_optional_artifact_binding_is_not_invented(binding):
    document = bundle()
    node = document["nodes"][0]
    node["source"].pop("artifact_id")
    document["documents"][0]["attributes"].pop("artifact_id")
    if binding == "no_artifact_identity":
        node.pop("artifact_id")
    else:
        document["artifacts"][0].pop("path")
    result = atlas.context(document, "renewals")
    assert result["items"][0]["source"] == node["source"]
    assert result["items"][0]["path"] == "handbook.md"
    assert "artifact_id" not in result["items"][0]["source"]


@pytest.mark.parametrize("source_value", [None, "omitted"])
def test_absent_source_metadata_preserves_valid_legacy_node_binding(source_value):
    document = bundle()
    node = document["nodes"][0]
    if source_value is None:
        node["source"] = None
    else:
        node.pop("source")
    result = atlas.context(document, "renewals")
    assert result["items"][0]["path"] == "handbook.md"
    assert "source" not in result["items"][0]


def test_identity_free_path_only_legacy_bundle_remains_supported():
    document = bundle()
    document["artifacts"] = []
    node = document["nodes"][0]
    node.pop("artifact_id")
    node["source"].pop("artifact_id")
    document["documents"][0]["attributes"].pop("artifact_id")
    result = atlas.context(document, "renewals")
    assert result["items"][0]["source"] == node["source"]
    assert "Lantern renewals are allowed once." in result["items"][0]["text"]


@pytest.mark.parametrize("version", ["before", "after", "old_retained"])
def test_current_rkc_document_source_and_evidence_bindings_are_retained(version):
    fixture = json.loads(
        (FIXTURES / "rkc_sinter_context_bridge_source_bound.v1.json").read_text()
    )
    packet = fixture["packets"][version]
    original = copy.deepcopy(packet)
    result = atlas.context(packet, "Lantern lending period")
    expected = next(row for row in packet["items"] if row["object_type"] == "document")
    retained = next(row for row in result["items"] if row["object_type"] == "document")
    assert expected["source"]["start_line"] == 1
    assert expected["source"]["end_line"] == 12
    assert expected["evidence_ids"]
    assert retained["source"] == expected["source"]
    assert retained["evidence_ids"] == expected["evidence_ids"]
    assert retained["id"] == expected["citation_id"]
    assert retained["text"] == expected["text"]
    assert packet == original


@pytest.mark.parametrize("negative", ["snapshot_only_swap", "citation_corruption"])
def test_current_rkc_fixture_negative_packets_are_rejected(negative):
    fixture = json.loads(
        (FIXTURES / "rkc_sinter_context_bridge_source_bound.v1.json").read_text()
    )
    with pytest.raises(ValueError, match="citation"):
        atlas.validate(fixture["negative_packets"][negative])


@pytest.mark.parametrize("version", ["before", "after"])
def test_retained_references_match_rkc_recorded_canonical_and_reimported_rows(version):
    fixture = json.loads(
        (FIXTURES / "rkc_sinter_context_bridge_source_bound.v1.json").read_text()
    )
    packet = fixture["packets"][version]
    result = atlas.context(packet, "Lantern lending period")
    retained = next(row for row in result["items"] if row["object_type"] == "document")
    producer = fixture["document_source_references"][version]
    assert retained["source"] == producer["document_source"]
    assert retained["evidence_ids"] == producer["document_evidence_ids"]
    assert sorted(retained["evidence_ids"]) == retained["evidence_ids"]
    assert set(retained["evidence_ids"]) == set(producer["resolved_evidence"])
    imported = producer["export_import"]["document"]
    assert retained["id"] == imported["citation_id"]
    assert retained["text"] == imported["text"]
    assert retained["source"] == imported["source"]
    assert retained["evidence_ids"] == imported["evidence_ids"]
