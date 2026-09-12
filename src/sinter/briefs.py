"""Deterministic document formats and lexical question navigation, not fact inference."""
from __future__ import annotations

import re

from .evidence import Excerpt, Source, excerpts, literal, text, tokens, validate_excerpt

FORMATS = {"enquiry": "Enquiry letter", "briefing": "Briefing note", "agenda": "Agenda item"}
QUESTION_WORDS = set("what when where who which how could would should please confirm provide does have has are can need available information about still stated supplied evidence source material relevant say says tell know".split())


def question_index(questions: str, sources: list) -> list[dict]:
    """Link each question to at most two exact excerpts; never label it answered."""
    queries = [line.strip().lstrip('-* ').strip() for line in questions.splitlines() if line.strip()]
    if len(queries) > 30:
        raise ValueError("Use no more than 30 questions per brief.")
    candidates = excerpts(sources)
    output = []
    for question in dict.fromkeys(queries):
        terms = tokens(question) - QUESTION_WORDS
        scored = sorted(((len(terms & tokens(row.quote)), row) for row in candidates),
                        key=lambda pair: pair[0], reverse=True)
        matches = []
        for score, row in scored:
            if not score or len(matches) == 2:
                break
            if not validate_excerpt(row, sources):
                raise ValueError("A question reference does not match its source.")
            matches.append({"source_id": row.source_id, "excerpt_id": row.id, "start": row.start,
                            "end": row.end, "quote": row.quote})
        output.append({"question": question, "status": "related_material" if matches else "no_keyword_match",
                       "matches": matches})
    return output


DOCUMENT_FIELDS = {
    "recipient": ("Recipient", 200), "signatory": ("Your name", 200),
    "organisation": ("Organisation", 1024), "sender_role": ("Your role", 200),
    "contact_details": ("Contact details", 4096),
}


def document_details(payload: dict) -> dict[str, str]:
    """Validate explicit document details; never fetch or infer a person's identity."""
    return {key: text(payload.get(key, ""), label, limit).strip()
            for key, (label, limit) in DOCUMENT_FIELDS.items()}


def document_questions(payload: dict) -> list[str]:
    """Use entered questions, or verbatim question sentences from the user's notes."""
    entered = text(payload.get("questions", ""), "Questions", 12000)
    if entered.strip():
        questions = [line.strip().lstrip("-* ").strip() for line in entered.splitlines()
                     if line.strip()]
    else:
        notes = text(payload.get("notes", ""), "Notes")
        questions = [match.group().strip().lstrip("-* ").strip()
                     for match in re.finditer(r"[^.!?\n]+\?", notes)]
    questions = list(dict.fromkeys(question for question in questions if question))
    if len(questions) > 30:
        raise ValueError("Use no more than 30 questions per brief.")
    return questions


def _quote(content: str) -> str:
    return "> " + literal(content).replace("\n", "\n> ")


def _context(payload: dict, sources: list[Source], selected: list[Excerpt],
             *, letter: bool) -> list[str]:
    """Keep short, exact source passages in the usable document, with plain attribution."""
    notes = text(payload.get("notes", ""), "Notes").strip()
    if letter and notes:
        if len(notes) <= 1600:
            return ["For context, our notes record:", _quote(notes)]
        # A long note belongs in the evidence pack; use an admitted exact passage here.
        selected_notes = [item for item in selected
                          if any(parent.id == item.source_id and parent.kind == "user_note"
                                 for parent in sources)]
        if selected_notes:
            return ["For context, this passage from our notes is relevant:",
                    _quote(selected_notes[0].quote)]
        return ["For context, the opening passage of our notes reads:", _quote(notes[:1200])]
    by_id = {item.id: item for item in sources}
    passages = selected[:2 if letter else 4]
    lines = []
    for passage in passages:
        if not validate_excerpt(passage, sources):
            raise ValueError("A document passage does not match its source. Rebuild the report.")
        parent = by_id[passage.source_id]
        if letter:
            lines.extend([f"The supplied material titled {literal(parent.title)} states:",
                          _quote(passage.quote)])
        else:
            lines.extend(["### " + literal(parent.title), _quote(passage.quote)])
        if parent.url:
            lines.append("Source: " + literal(parent.url))
    return lines


def prepare_document(payload: dict, sources: list[Source],
                     selected: list[Excerpt] | None = None) -> dict:
    """Build a usable document separately from its evidence and completion guidance."""
    kind = payload.get("document_type", "enquiry")
    if not isinstance(kind, str) or kind not in FORMATS:
        raise ValueError("Choose enquiry, briefing or agenda as the document type.")
    title = text(payload.get("title", ""), "Title", 200, True)
    details = document_details(payload)
    questions = document_questions(payload)
    selected = excerpts(sources)[:4] if not selected else selected
    context = _context(payload, sources, selected, letter=kind == "enquiry")
    question_list = "\n".join(f"{index}. {literal(question)}"
                              for index, question in enumerate(questions, 1))
    missing = []
    if kind == "enquiry":
        if not questions:
            missing.append({"field": "questions", "label": "Questions you want answered"})
        if not details["signatory"]:
            missing.append({"field": "signatory", "label": "Your name or sign-off"})
        if not details["contact_details"]:
            missing.append({"field": "contact_details", "label": "Your reply contact details"})
        greeting = "Dear " + literal(details["recipient"]) + "," if details["recipient"] else "Hello,"
        opening = ("I am writing on behalf of " + literal(details["organisation"]) + " about "
                   if details["organisation"] else "I am writing about ") + literal(title) + "."
        lines = [greeting, "Re: " + literal(title), opening, *context]
        if questions:
            lines.extend(["Could you please clarify the following?", question_list,
                          "Please include any relevant details or links in your response."])
        lines.append("Thank you for your help.")
        signature = [details[key] for key in ("signatory", "sender_role", "organisation", "contact_details")
                     if details[key]]
        if signature:
            lines.extend(["Kind regards,", "\n".join(literal(value) for value in dict.fromkeys(signature))])
    elif kind == "agenda":
        lines = ["# " + literal(title), "## Purpose", "Discuss the supplied background and agree the next steps."]
        if details["signatory"]:
            lines.append("Prepared by: " + literal(details["signatory"]))
        if context:
            lines.extend(["## Background", *context])
        if questions:
            lines.extend(["## Questions for discussion", question_list])
        lines.extend(["## Proposed next steps",
                      "- Agree which points need clarification before making a decision.\n"
                      "- Assign a person to obtain each outstanding answer.\n"
                      "- Agree when the item should return for review."])
    else:
        lines = ["# " + literal(title)]
        if details["recipient"]:
            lines.append("Prepared for: " + literal(details["recipient"]))
        if details["signatory"]:
            lines.append("Prepared by: " + literal(details["signatory"]))
        if details["organisation"]:
            lines.append(literal(details["organisation"]))
        if context:
            lines.extend(["## Background", *context])
        if questions:
            lines.extend(["## Questions requiring clarification", question_list])
        lines.extend(["## Recommended next steps",
                      "- Review the background and confirm which information is current.\n"
                      "- Resolve the open questions with the relevant people or source owners.\n"
                      "- Record the agreed response and who will follow it up."])
    return {"document_markdown": "\n\n".join(lines), "document_title": title,
            "document_type": kind, "document_details": details,
            "document_questions": questions, "missing_fields": missing,
            "document_ready": not missing}


def sections(payload: dict, sources: list, prepared: dict | None = None) -> tuple[list[str], list[dict]]:
    prepared = prepare_document(payload, sources) if prepared is None else prepared
    heading = {"enquiry": "Draft enquiry letter", "agenda": "Draft agenda item",
               "briefing": "Briefing note"}[prepared["document_type"]]
    lines = ["## " + heading, prepared["document_markdown"]]
    index = question_index("\n".join(prepared["document_questions"]), sources)
    if index:
        lines += ["## Question-to-source guide", "Keyword matches help you navigate. They do not establish that a question has been answered, or that the source is current, authoritative or complete."]
        for row in index:
            lines.append("### " + literal(row["question"]))
            if not row["matches"]:
                lines.append("No keyword match found. Read the full sources and request clarification; this is not proof that the information is absent.")
            for match in row["matches"]:
                lines.append(f"[{match['source_id']}] characters {match['start']}-{match['end']} (related wording; review context):\n\n> " + literal(match["quote"]).replace("\n", "\n> "))
    return lines, index
