"""Source-constrained community workflows over the public API."""
from __future__ import annotations

from dataclasses import asdict

from . import client
from .evidence import MAX_CONTEXT, collect, literal, render_evidence, select, source, text, utc_now
from .grants import screen
from .meetings import minutes

WORKFLOWS = {
    "research": {"name": "Research a topic", "description": "Explore source highlights, citations and questions to investigate."},
    "grants": {"name": "Find funding", "description": "Discover opportunities and check what is still unknown."},
    "brief": {"name": "Build a brief & letter", "description": "Bring notes and references into a traceable enquiry."},
    "meeting": {"name": "Prepare minutes", "description": "Preserve speaker turns and review corrections transparently."},
}


def run(payload: dict, progress=lambda message: None) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Provide a workflow object.")
    kind = payload.get("workflow", "brief")
    if not isinstance(kind, str) or kind not in WORKFLOWS:
        raise ValueError("Choose a research, funding, briefing or meeting workflow.")
    title = text(payload.get("title", ""), "Project title", 200, True)
    notes = text(payload.get("notes", ""), "Notes", 1000000 if kind == "meeting" else MAX_CONTEXT)
    query = text(payload.get("query", ""), "Search query", 1024)
    questions = text(payload.get("questions", ""), "Questions", 12000)
    for flag in ("use_search", "use_model", "demo"):
        if flag in payload and type(payload[flag]) is not bool:
            raise ValueError(f"{flag} must be a boolean.")
    demo = payload.get("demo", False)
    if demo and (payload.get("use_search") or payload.get("use_model")):
        raise ValueError("Examples run offline. Start a new project before using live services.")
    warnings = ["Review before sending or tabling. No automated process guarantees hallucination-free or legally correct work."]
    if demo:
        warnings.append("ILLUSTRATIVE EXAMPLE: people, funding and organisation details are fictional.")
    result = {"workflow": kind, "title": title, "created_at": utc_now(), "demo": demo,
              "review_status": "draft", "warnings": warnings, "sources": [], "excerpts": []}
    if kind == "meeting":
        if payload.get("use_search") or payload.get("use_model"):
            raise ValueError("Minutes are processed locally. Do not enable web search or model ranking for transcripts.")
        progress("Preserving the transcript and speaker labels")
        result.update(minutes(title, notes, payload.get("speaker_map"), payload.get("corrections")))
        if demo:
            result["markdown"] = "ILLUSTRATIVE EXAMPLE - FICTIONAL MEETING\n\n" + result["markdown"]
        result["sources"] = [asdict(source("Original transcript", notes, kind="transcript"))]
        progress("Ready for chair and speaker review")
        return result
    progress("Collecting your notes and references")
    sources = collect(payload.get("sources", []), notes)
    if payload.get("use_search"):
        if not query.strip():
            raise ValueError("Enter the exact query you want to send to the search service.")
        progress("Searching NeuroForge for your exact query")
        response = client.search(query)
        used, added = sum(len(item.content) for item in sources), 0
        for item in response.results[:12]:
            if not item.content.strip():
                continue
            if used + len(item.content) > MAX_CONTEXT or len(sources) >= 60:
                warnings.append("Some search excerpts were omitted to keep the context within its safety limits.")
                break
            sources.append(source(item.title or "Search result", item.content, item.url, "search_excerpt", response.retrieved_at))
            used += len(item.content)
            added += 1
        sources = list({item.id: item for item in sources}.values())
        if not added:
            warnings.append("Search returned no usable additional evidence. Only supplied context is used.")
        warnings.append("Search results are excerpts, not full guidelines or verified authoritative sources.")
    if not sources:
        raise ValueError("Add notes or a reference, or enable search with a query.")
    progress("Selecting traceable excerpts with source diversity")
    selected, selection_warnings = select(sources, title + " " + query + " " + questions, payload.get("use_model", False))
    warnings.extend(selection_warnings)
    lines = [f"# {literal(title)}", "DRAFT - HUMAN REVIEW REQUIRED", f"Prepared: {result['created_at']}"]
    if demo:
        lines.append("ILLUSTRATIVE EXAMPLE - " + ("NOT REAL GRANT INFORMATION" if kind == "grants" else "FICTIONAL SOURCE MATERIAL"))
    if kind == "grants":
        lines.extend(["## Funding discovery and screening",
                      "These are leads, not confirmed open grants. Check the funder's current programme page. "
                      "Do not infer eligibility from a title, excerpt or model suggestion.",
                      "## Requirements to check for every opportunity",
                      "Applicant legal structure; geography; eligible expenditure; exclusions; co-contribution; "
                      "amount limits; opening/closing date and time zone; evidence needed; official contact.",
                      "## Deadline status", "Unconfirmed. Only dates explicitly checked by a person should become reminders."])
        result["screening"] = screen(payload.get("profile", {}), payload.get("criteria", []), sources)
        if result["screening"]["checks"]:
            lines.append(result["screening"]["markdown"])
    elif kind == "research":
        from .research import sections
        document, metadata = sections(title, query, questions, sources, selected)
        lines.extend(document)
        result.update(metadata)
        result["document_type"] = "research"
    else:
        from .briefs import sections
        document, question_map = sections(payload, sources)
        lines.extend(document)
        result["document_type"] = payload.get("document_type", "enquiry")
        result["question_index"] = question_map
    progress("Checking every excerpt against its original source")
    if kind != "research":
        lines.append(render_evidence(selected, sources))
    lines.extend(["## Limitations and review", "\n".join("- " + literal(warning) for warning in warnings)])
    result.update({"markdown": "\n\n".join(lines), "sources": [asdict(item) for item in sources],
                   "excerpts": [asdict(item) for item in selected]})
    return result


def example(kind: str) -> dict:
    if not isinstance(kind, str) or kind not in WORKFLOWS:
        raise ValueError("Unknown example.")
    common = {"workflow": kind, "demo": True, "use_search": False, "use_model": False}
    if kind == "research":
        return {**common, "title": "Planning an accessible community garden",
                "query": "community garden accessible paths water planning",
                "questions": "What accessible paths and seating should we check?\nWhat is still undecided about water?",
                "sources": [
                    {"title": "Fictional garden access notes", "kind": "sample", "content":
                     "The proposed community garden has a level entrance. Path widths have not been measured.\n"
                     "Ask participants about accessible paths, seating and raised garden beds before choosing a layout."},
                    {"title": "Fictional volunteer planning notes", "kind": "sample", "content":
                     "The garden group needs to confirm water access with the venue. No irrigation budget has been approved.\n"
                     "Two volunteers offered to gather water-saving options for the next planning meeting."}]}
    if kind == "grants":
        return {**common, "title": "Example school garden funding", "query": "community school garden grants",
                "notes": "FICTIONAL EXAMPLE: Riverbank P&C wants a small school garden. No real funding is represented.",
                "profile": {"organisation_type": "P&C", "location": "Queensland", "budget": "3000"},
                "sources": [{"title": "Fictional garden programme - demonstration only", "kind": "sample",
                             "content": "This fictional example supports school garden materials.\n"
                                        "Applicant status and co-contribution must be checked.\nNo real closing date or grant offer is provided."}]}
    if kind == "meeting":
        return {**common, "title": "Example community garden meeting", "notes":
                "SPEAKER_01: We discussed the garden but did not approve spending.\n"
                "SPEAKER_02: I will ask for two quotes before the next meeting.\nSPEAKER_01: No vote was taken today.",
                "speaker_map": {"SPEAKER_01": "Alex (fictional)", "SPEAKER_02": "Sam (fictional)"}}
    return {**common, "title": "Example community venue enquiry", "query": "venue access arrangements",
            "notes": "FICTIONAL EXAMPLE: Our volunteer group is considering a meeting at a community venue. "
                     "Availability and accessibility arrangements have not been confirmed.",
            "questions": "What accessible entry and hearing assistance are available?\n"
                         "Who approves recurring bookings, and what costs and notice periods apply?",
            "sources": [{"title": "Fictional venue notice", "kind": "sample", "content":
                         "Bookings are subject to confirmation by the venue coordinator.\nGroups should contact the venue to confirm access needs."}]}
