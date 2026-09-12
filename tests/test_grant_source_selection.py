"""Human-readable grant source selection preserves evidence and authority checks."""
from dataclasses import asdict
from unittest.mock import patch

import pytest

from sinter.evidence import source
from sinter.grants import screen
from sinter.workbench import run


@pytest.fixture
def reference():
    return source("Budget guideline", "Project budgets must not exceed $5,000.",
                  "https://example.org/fictional-guide", "reference_excerpt")


def requirement(reference, **changes):
    return {"field": "budget", "operator": "maximum", "value": 5000,
            "source_title": reference.title, "quote": reference.content,
            "confirmed": True, **changes}


def test_title_resolves_to_canonical_source_identity(reference):
    result = screen({"budget": 4000}, [requirement(reference)], [reference])
    check = result["checks"][0]
    assert check["status"] == "met"
    assert check["source_id"] == reference.id
    assert check["source_title"] == reference.title
    assert check["quote"] in reference.content
    assert result["status"] == "review_required"
    assert f"[{reference.id}]" in result["markdown"]


def test_matching_title_and_identifier_are_allowed(reference):
    rule = requirement(reference, source_id=reference.id)
    assert screen({"budget": 6000}, [rule], [reference])["checks"][0]["status"] == "not_met"


@pytest.mark.parametrize("title", ["budget guideline", " Budget guideline", "Budget guideline ", "Unknown"])
def test_title_must_match_exactly(reference, title):
    with pytest.raises(ValueError, match="exact source_title"):
        screen({"budget": 4000}, [requirement(reference, source_title=title)], [reference])


@pytest.mark.parametrize("title", [None, [], 7, "", " " * 3, "x" * 501])
def test_invalid_title_is_not_ignored_even_with_a_valid_identifier(reference, title):
    with pytest.raises(ValueError, match="[Ss]ource title"):
        screen({"budget": 4000}, [requirement(reference, source_title=title, source_id=reference.id)], [reference])


@pytest.mark.parametrize("include_identifier", [False, True])
def test_ambiguous_title_never_selects_a_source_arbitrarily(reference, include_identifier):
    other = source(reference.title, "Different budget guidance.", kind="reference_excerpt")
    rule = requirement(reference)
    if include_identifier:
        rule["source_id"] = reference.id
    with pytest.raises(ValueError, match="matches more than one source"):
        screen({"budget": 4000}, [rule], [reference, other])


def test_repeated_same_source_identity_is_not_a_different_source(reference):
    check = screen({"budget": 4000}, [requirement(reference)], [reference, reference])["checks"][0]
    assert check["source_id"] == reference.id and check["status"] == "met"


@pytest.mark.parametrize("known_identifier", [False, True])
def test_conflicting_title_and_identifier_fail(reference, known_identifier):
    other = source("Other guide", "Different budget guidance.", kind="reference_excerpt")
    rule = requirement(reference, source_id=other.id if known_identifier else "Sunknown")
    with pytest.raises(ValueError, match="identify different sources"):
        screen({"budget": 4000}, [rule], [reference, other])


@pytest.mark.parametrize("changes,reason", [
    ({"quote": "Invented requirement"}, "does not match"),
    ({"quote": ""}, "wording is missing"),
    ({"confirmed": False}, "A person must confirm"),
    ({"confirmed": "yes"}, "A person must confirm"),
])
def test_title_selection_does_not_bypass_quote_or_confirmation(reference, changes, reason):
    check = screen({"budget": 4000}, [requirement(reference, **changes)], [reference])["checks"][0]
    assert check["status"] == "unknown" and reason in check["reason"]


@pytest.mark.parametrize("kind", ["sample", "user_note", "transcript"])
def test_title_selection_never_promotes_non_authoritative_sources(kind):
    reference = source("Budget notes", "Project budgets must not exceed $5,000.", kind=kind)
    check = screen({"budget": 4000}, [requirement(reference)], [reference])["checks"][0]
    assert check["status"] == "unknown" and "cannot establish official" in check["reason"]


def test_existing_identifier_path_keeps_unknown_reference_behavior(reference):
    rule = requirement(reference, source_id="Sunknown")
    rule.pop("source_title")
    check = screen({"budget": 4000}, [rule], [reference])["checks"][0]
    assert check["status"] == "unknown" and check["source_id"] == "Sunknown"


def test_workbench_json_can_use_titles_without_computing_hashes(reference):
    payload = {"workflow": "grants", "title": "Fictional budget check", "sources": [asdict(reference)],
               "profile": {"budget": 4000}, "criteria": [requirement(reference)],
               "use_search": False, "use_model": False}
    with patch("sinter.client.search") as search, patch("sinter.client.chat") as chat:
        result = run(payload)
    check = result["screening"]["checks"][0]
    assert check["source_title"] == "Budget guideline"
    assert check["source_id"] == result["sources"][0]["id"]
    assert check["status"] == "met" and result["screening"]["status"] == "review_required"
    search.assert_not_called()
    chat.assert_not_called()
