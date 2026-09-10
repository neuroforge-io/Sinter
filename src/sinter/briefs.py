"""Deterministic document formats and lexical question navigation, not fact inference."""
from __future__ import annotations

from .evidence import excerpts, literal, text, tokens, validate_excerpt

FORMATS = {"enquiry": "Enquiry letter", "briefing": "Briefing note", "agenda": "Agenda item"}
QUESTION_WORDS = set("what when where who which how could would should please confirm provide does have has are can need available information".split())


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


def sections(payload: dict, sources: list) -> tuple[list[str], list[dict]]:
    format = payload.get("document_type", "enquiry")
    if not isinstance(format, str) or format not in FORMATS:
        raise ValueError("Choose enquiry, briefing or agenda as the document type.")
    title = literal(text(payload.get("title", ""), "Title", 200, True))
    questions = text(payload.get("questions", ""), "Questions", 12000)
    recipient = literal(text(payload.get("recipient", ""), "Recipient", 200)) or "[recipient]"
    signatory = literal(text(payload.get("signatory", ""), "Signatory", 200)) or "[Name]"
    organisation = literal(text(payload.get("organisation", ""), "Organisation", 200)) or "[Organisation]"
    question_text = literal(questions) if questions.strip() else "[Add the questions requiring a response.]"
    if format == "enquiry":
        lines = ["## Draft enquiry letter", f"Dear {recipient},", f"Re: {title}",
            "We are seeking clarification on the questions below. The accompanying evidence pack reproduces material for checking; "
            "we have not treated unverified notes or search excerpts as settled facts.", question_text,
            "Please identify the current policy, guideline or other source supporting your response, and clarify any point where our information is incomplete or out of date.",
            f"Thank you for your assistance.\n\n{signatory}\n{organisation}\n[Contact details]"]
    elif format == "agenda":
        lines = ["## Draft agenda item", f"Item: {title}", "Purpose: discussion and clarification; no decision has been recorded.",
            "## Questions for discussion", question_text, "## Background material", "See the exact excerpts and source register below. Notes remain assertions, not independently verified facts.",
            "## Proposed next step", "[For the meeting to determine: information required, responsible person and review date.]",
            "No motion, seconder, vote or approved outcome is inferred by this draft."]
    else:
        lines = ["## Briefing note", f"Subject: {title}", f"Prepared for: {recipient}",
            "## Scope", "A compilation of supplied context and references, not a finding or an independent investigation.",
            "## Questions requiring an answer", question_text, "## Background and evidence", "Exact excerpts and their source records follow below.",
            "## Next step", "[Review the full source material and record the requested decision or response.]"]
    index = question_index(questions, sources)
    if index:
        lines += ["## Question-to-source guide", "Keyword matches help you navigate. They do not establish that a question has been answered, or that the source is current, authoritative or complete."]
        for row in index:
            lines.append("### " + literal(row["question"]))
            if not row["matches"]:
                lines.append("No keyword match found. Read the full sources and request clarification; this is not proof that the information is absent.")
            for match in row["matches"]:
                lines.append(f"[{match['source_id']}] characters {match['start']}-{match['end']} (related wording; review context):\n\n> " + literal(match["quote"]).replace("\n", "\n> "))
    return lines, index
