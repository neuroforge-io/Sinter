"""Actual Go exports may represent empty optional collections as JSON null."""
import json
import pytest
from sinter import atlas
from test_desktop_atlas import packet


def test_rkc_nil_optional_collections_keep_provenance():
    value = {'snapshot': {'schema_version': '0.2.0', 'id': 'fixture'},
             'artifacts': [], 'nodes': [{'id': 'n1', 'name': 'garden', 'kind': 'function'}],
             'edges': None, 'evidence': None, 'diagnostics': None}
    original = json.dumps(value)
    assert atlas.inspect(value)['item_count'] == 1
    assert json.dumps(value) == original
    value['nodes'] = None
    with pytest.raises(ValueError):
        atlas.validate(value)


def test_rkc_nil_context_references_are_empty_not_fabricated():
    value = packet()
    value['items'][0]['evidence_ids'] = None
    value['warnings'] = None
    view = atlas.validate(value)
    assert view['items'][0]['evidence_ids'] == []
    assert value['items'][0]['evidence_ids'] is None
