"""Campaign correspondence must never inherit the runner's personal sign-off."""
import pytest

from sinter.campaigns import validate
from sinter.workbench import run


def test_campaign_identity_defaults_to_blank_and_preserves_explicit_values():
    base = {"schema": "sinter-campaign/v1", "title": "Fictional school swim plan"}
    blank = validate(base)
    assert blank["signatory"] == ""
    assert blank["sender_role"] == ""
    assert blank["contact_details"] == ""

    explicit = validate({**base, "signatory": "Casey Example",
                         "sender_role": "P&C President",
                         "contact_details": "campaign@example.invalid\n0400 222 333"})
    assert explicit["signatory"] == "Casey Example"
    assert explicit["sender_role"] == "P&C President"
    assert explicit["contact_details"] == "campaign@example.invalid\n0400 222 333"


@pytest.mark.parametrize("field, value, message", [
    ("signatory", "S" * 201, "Authorised campaign signatory"),
    ("sender_role", "R" * 201, "Campaign signatory role"),
    ("contact_details", "C" * 4097, "Campaign contact details"),
])
def test_campaign_identity_fields_are_bounded(field, value, message):
    with pytest.raises(ValueError, match=message):
        validate({"schema": "sinter-campaign/v1", "title": "Fictional campaign",
                  field: value})


def test_organisation_name_alone_does_not_create_a_signed_closing():
    report = run({
        "workflow": "brief", "title": "Confirm the swimming programme",
        "document_type": "enquiry", "recipient": "School principal",
        "organisation": "Waraburra School Association",
        "notes": "The programme and costs still need confirmation.",
        "questions": "Which costs are approved?", "use_search": False,
        "use_model": False,
    })
    document = report["document_markdown"]
    assert "I am writing on behalf of Waraburra School Association" in document
    assert "Kind regards," not in document
    assert document.endswith("Thank you for your help.")
    assert {row["field"] for row in report["missing_fields"]} >= {
        "signatory", "contact_details",
    }


def test_explicit_campaign_signer_and_contact_render_in_the_closing():
    report = run({
        "workflow": "brief", "title": "Confirm the swimming programme",
        "document_type": "enquiry", "recipient": "School principal",
        "organisation": "Waraburra School Association",
        "signatory": "Casey Example", "sender_role": "P&C President",
        "contact_details": "campaign@example.invalid",
        "notes": "The programme and costs still need confirmation.",
        "questions": "Which costs are approved?", "use_search": False,
        "use_model": False,
    })
    document = report["document_markdown"]
    assert "Kind regards," in document
    assert all(value in document for value in (
        "Casey Example", "P&amp;C President", "Waraburra School Association",
        "campaign@example.invalid",
    ))
    assert report["document_ready"]


def test_campaign_clarification_uses_scoped_context_without_claiming_authority():
    report = run({
        "workflow": "brief", "title": "Clarification: CSIRO RUIC eligibility and project scope",
        "document_type": "enquiry", "recipient": "CSIRO RUIC programme team",
        "organisation": "NeuroforgeIO Pty Ltd",
        "campaign_sender_review": True,
        "notes": "NeuroforgeIO Pty Ltd is assessing a possible under-12-month Queensland university collaboration. The partner, budget and eligibility are not confirmed.",
        "questions": "Which operating-age rule applies?\nWhat cash-match evidence is required?",
        "use_search": False, "use_model": False,
    })
    document = report["document_markdown"]
    assert "Re: CSIRO RUIC eligibility and project scope" in document
    assert "NeuroforgeIO Pty Ltd is assessing whether this programme could support a defined project" in document
    assert "The partner, budget and eligibility are not confirmed." in document
    assert "For context, our notes record" not in document
    assert "I am writing on behalf of" not in document
    assert "Kind regards," not in document
    assert {row["field"] for row in report["missing_fields"]} >= {"signatory", "contact_details"}
