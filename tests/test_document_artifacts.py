"""Usable document exports stay separate from provenance and unfinished details."""
import copy
import json
import re
from unittest.mock import patch

import pytest

from sinter import casebooks, client
from sinter.briefs import document_details
from sinter.profiles import sender_defaults
from sinter.recipes import community_recipes
from sinter.templates import _from_data, get_builtin_template, template_events
from sinter.workbench import example, run


SENDER = {"signatory": "Alex Morgan", "sender_role": "Secretary",
          "organisation": "Banksia Neighbourhood Group",
          "contact_details": "alex@example.org\n+61 7 5550 1234"}
PLACEHOLDER = re.compile(r"\[(?:recipient|name|organisation|organization|contact details|sender[^\]]*|add[^\]]*|for the meeting[^\]]*|review the full[^\]]*|to confirm)\]", re.I)


def project(**changes):
    return {"workflow": "brief", "title": "River Hall workshop access", "document_type": "enquiry",
            "recipient": "River Hall coordinator", **SENDER,
            "notes": "The booking has NOT been approved. Wheelchair access has not been confirmed.",
            "questions": "Is River Hall available on 14 October?\nDoes it have an accessible toilet?",
            "sources": [{"title": "Hall coordinator's note", "content": "The hall booking is provisional. Check access before advertising.",
                         "url": "https://example.org/hall"}], "use_search": False, "use_model": False, **changes}


def test_enquiry_is_a_usable_letter_with_visible_exact_sender_and_context():
    payload = project()
    before = copy.deepcopy(payload)
    with patch("sinter.client.chat") as model, patch("sinter.client.search") as search:
        result = run(payload)
    document = result["document_markdown"]
    assert document.startswith("Dear River Hall coordinator,")
    assert "The booking has NOT been approved." in document
    assert "1. Is River Hall available on 14 October?" in document
    assert "2. Does it have an accessible toilet?" in document
    assert all(value in document for value in (SENDER["signatory"], SENDER["sender_role"], SENDER["organisation"], "alex@example.org"))
    assert "Kind regards," in document and not PLACEHOLDER.search(document)
    assert result["document_ready"] and result["missing_fields"] == []
    assert not any(term in document for term in ("SHA-256", "characters", "Keyword matches", "evidence pack", "independently verified"))
    assert "SHA-256" in result["markdown"] and result["sources"] and result["question_index"]
    assert payload == before
    model.assert_not_called(); search.assert_not_called()


def test_unfilled_enquiry_reports_details_outside_the_document():
    result = run(project(recipient="", signatory="", organisation="", sender_role="", contact_details="", questions=""))
    document = result["document_markdown"]
    assert document.startswith("Hello,") and not PLACEHOLDER.search(document)
    assert "questions below" not in document and "Could you please clarify the following?" not in document
    assert "Kind regards" not in document
    assert {row["field"] for row in result["missing_fields"]} == {"questions", "signatory", "contact_details"}
    assert result["document_ready"] is False


def test_only_actual_questions_in_notes_are_reused():
    result = run(project(questions="", notes="The booking is provisional. Is access step-free?\nWhen can we collect the keys?"))
    assert result["document_questions"] == ["Is access step-free?", "When can we collect the keys?"]
    assert result["document_ready"]
    assert "The booking is provisional." in result["document_markdown"]
    assert "The booking is provisional." not in result["document_questions"]


@pytest.mark.parametrize("kind", ["briefing", "agenda"])
def test_briefing_and_agenda_contain_actual_background_and_no_scaffold(kind):
    result = run(project(document_type=kind))
    document = result["document_markdown"]
    assert "The booking has NOT been approved." in document
    assert "Is River Hall available on 14 October?" in document
    assert "Alex Morgan" in document and not PLACEHOLDER.search(document)
    assert "See the exact excerpts" not in document
    assert "next steps" in document.lower()
    assert "Source register" in result["markdown"]


def test_briefing_keeps_supplied_background_even_without_a_keyword_match():
    result = run(project(title="Untitled", document_type="briefing", questions="",
                         notes="Rain delayed the working bee.", sources=[]))
    assert "Rain delayed the working bee." in result["document_markdown"]


def test_sender_details_are_explicit_and_accept_all_valid_profile_defaults():
    profile = {"full_name": "Alex Morgan", "role": "Secretary", "organisation": "A" * 1024,
               "email": "alex@example.org", "phone": "1234", "website": "https://example.org/" + "a" * 1800}
    defaults = sender_defaults(profile)
    result = run(project(**{key: value for key, value in defaults.items() if key in document_details({})}))
    assert result["document_details"]["contact_details"] == defaults["contact_details"]
    assert result["document_details"]["organisation"] == profile["organisation"]
    assert run(project(signatory=""))["document_details"]["signatory"] == ""


def test_research_clean_document_preserves_source_highlights_without_audit_ids():
    result = run(project(workflow="research"))
    document = result["document_markdown"]
    assert "The hall booking is provisional." in document
    assert "https://example.org/hall" in document
    assert "Questions to investigate" in document
    assert not PLACEHOLDER.search(document)
    assert all(item["id"] not in document for item in result["excerpts"])
    assert "Source register" in result["markdown"]


def test_funding_document_has_a_per_source_shortlist_and_actual_check_status():
    sources = [{"title": "Fictional garden grant", "content": "Project budgets must not exceed $5,000.", "url": "https://example.org/garden"},
               {"title": "Fictional community fund", "content": "Applicants must supply an access plan.", "url": "https://example.org/community"}]
    rule = {"field": "budget", "operator": "maximum", "value": 5000, "source_title": sources[0]["title"],
            "quote": sources[0]["content"], "confirmed": True}
    result = run(project(workflow="grants", sources=sources, profile={"budget": 4000}, criteria=[rule]))
    document = result["document_markdown"]
    assert all(row["title"] in document and row["content"] in document and row["url"] in document for row in sources)
    assert "Matches the entered requirement" in document and "Your value: 4000" in document
    assert "Requirements have not been checked for this source yet." in document
    assert "1 matched; 0 did not match; 0 still need checking" in document
    assert "eligible" not in document and not PLACEHOLDER.search(document)
    assert len(result["sources"]) == 3  # Original user notes remain in the evidence pack.


def test_minutes_surface_recorded_actions_and_negated_decisions_without_inference():
    result = run(project(workflow="meeting", notes="Alex: I will ask the venue about the ramp.\nSam: Spending was NOT approved.\nAlex: The room was warm.",
                         speaker_map={"Alex": "Alex Morgan"}))
    document = result["document_markdown"]
    assert "Actions mentioned in the record" in document and "Decision and voting statements" in document
    assert "I will ask the venue about the ramp." in document and "Spending was NOT approved." in document
    assert "Alex Morgan" in document and "Other discussion" in document
    assert "Transcript record" not in document and not PLACEHOLDER.search(document)
    assert "Transcript record" in result["markdown"] and len(result["segments"]) == 3


@pytest.mark.parametrize("workflow", ["brief", "research", "grants", "meeting"])
def test_offline_examples_have_usable_documents_and_keep_the_fiction_label(workflow):
    result = run(example(workflow))
    assert result["document_markdown"] and "Fictional example" in result["document_markdown"]
    assert not PLACEHOLDER.search(result["document_markdown"])
    assert result["missing_fields"] == [] and result["document_ready"]
    if workflow == "brief":
        assert "Alex Morgan (fictional)" in result["document_markdown"]
        assert "alex@example.org" in result["document_markdown"]


def test_casebook_details_survive_validation_and_change_its_fingerprint():
    payload = {"title": "Workshop", "questions": "Is the hall booking approved?", **SENDER, "recipient": "Hall coordinator",
               "documents": [{"title": "Hall note", "content": "The hall booking is not approved."}]}
    book = casebooks.validate(payload)
    assert casebooks.validate(book) == book
    assert all(book[key] == value for key, value in SENDER.items())
    assert casebooks.validate({**payload, "signatory": "Jamie"})["fingerprint"] != book["fingerprint"]
    report = casebooks.build(book, "enquiry")
    assert "Alex Morgan" in report["document_markdown"] and "alex@example.org" in report["document_markdown"]
    assert "The hall booking is not approved." in report["document_markdown"]
    assert report["document_ready"] and not PLACEHOLDER.search(report["document_markdown"])
    assert report["source_register"] and report["casebook_fingerprint"] == book["fingerprint"]


def test_casebook_model_body_and_source_document_stay_distinct_and_sender_is_not_uploaded():
    payload = {"title": "Workshop", "questions": "Is the hall booking approved?", **SENDER,
               "documents": [{"title": "Hall note", "content": "The hall booking is not approved."}]}
    report = casebooks.build(payload, "enquiry")
    quote_id = report["excerpts"][0]["id"]
    with patch("sinter.client.chat", return_value=client.ChatResult(f"Please confirm the booking [{quote_id}]", finish_reason="stop")) as model:
        draft = casebooks.draft(report, True)
    assert "alex@example.org" in draft["document_markdown"]
    assert "alex@example.org" not in json.dumps([message.content for message in model.call_args.args[0]])
    assert draft["source_document_markdown"] == report["document_markdown"]
    assert draft["model_draft"] and "UNVERIFIED" in draft["markdown"]
    assert draft["sources"] == report["sources"] and draft["excerpts"] == report["excerpts"]


@pytest.mark.parametrize("name", community_recipes())
def test_recipes_use_visible_sender_and_select_draft_separately_from_review(name):
    template = get_builtin_template(name)
    sender = json.dumps(SENDER)
    values = {key: "Fictional source data" for key in template.variables}
    with patch("sinter.templates.chat", return_value=client.ChatResult("Body", finish_reason="stop")) as model:
        events = list(template_events(template, {**values, "sender": sender}, stream=False))
    assert template.output_step == 1 and template.review_step == 2
    assert [event["output_role"] for event in events if event["type"] == "step_done"] == ["supporting", "document", "review"]
    assert sender not in model.call_args_list[0].args[0][-1].content
    if name in {"enquiry-letter", "consultation-questions", "newsletter"}:
        assert all(sender in call.args[0][-1].content for call in model.call_args_list[1:])
    else:
        assert all(sender not in call.args[0][-1].content for call in model.call_args_list)
    assert all("[TO CONFIRM]" not in call.args[0][-1].content for call in model.call_args_list)


@pytest.mark.parametrize("data", [{"output_step": 3}, {"output_step": True}, {"review_step": -1}, {"review_step": 0}])
def test_template_output_metadata_rejects_ambiguous_or_invalid_positions(data):
    with pytest.raises(ValueError):
        _from_data({"steps": [{"name": "Only", "prompt": "Text"}], **data}, "fixture")
