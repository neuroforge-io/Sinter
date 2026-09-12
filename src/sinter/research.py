"""Build useful, source-backed research briefs without inventing a synthesis.

Selection is lexical and every highlight retains its original source offsets.
This module formats research; collection and optional ranking belong to workbench.
"""
from __future__ import annotations

from dataclasses import asdict

from .briefs import question_index
from .evidence import Excerpt, Source, literal, render_source_register, validate_excerpt


def sections(
    topic: str, query: str, questions: str,
    sources: list[Source], selected: list[Excerpt],
) -> tuple[list[str], dict]:
    """Return a research document and machine-readable evidence coverage."""
    by_id = {item.id: item for item in sources}
    represented = {item.source_id for item in selected}
    focuses = questions.strip() or topic
    index = question_index(focuses, sources)
    lines = [
        "## Research brief",
        "A starting point for your research: relevant wording from the collected "
        "sources, with links, context and questions to investigate. Highlights "
        "are exact excerpts; they are not independently verified conclusions.",
        "## Research scope",
        f"Topic: {literal(topic)}",
        f"Search query: {literal(query)}" if query else "Source collection: supplied material only.",
        f"Collected {len(sources)} source(s). Selected {len(selected)} excerpt(s) "
        f"from {len(represented)} source(s) using wording overlap and source diversity.",
        "## Source highlights",
    ]
    highlights = []
    for position, excerpt in enumerate(selected, 1):
        if not validate_excerpt(excerpt, sources):
            raise ValueError("A research excerpt no longer matches its source. Rebuild the report.")
        parent = by_id[excerpt.source_id]
        lines.extend([
            f"### {position}. {literal(parent.title)}",
            "> " + literal(excerpt.quote).replace("\n", "\n> "),
            f"[{excerpt.id}] Source: {parent.id}; characters {excerpt.start}–{excerpt.end}.",
            "Read the source: " + (literal(parent.url) if parent.url else "supplied locally"),
        ])
        highlights.append({**asdict(excerpt), "title": parent.title, "url": parent.url})
    if not selected:
        lines.append("No excerpts matched the topic wording. Try a more specific query "
                     "or inspect the full source material below. No answer has been inferred.")
    lines.extend([
        "## Questions to investigate",
        "Related wording helps you find a starting point. A match does not mean "
        "the question is answered.",
    ])
    for row in index:
        lines.append("### " + literal(row["question"]))
        if row["matches"]:
            for match in row["matches"]:
                lines.extend([
                    f"Related wording: {literal(by_id[match['source_id']].title)} "
                    f"[{match['excerpt_id']}]",
                    "> " + literal(match["quote"]).replace("\n", "\n> "),
                    f"Source: {match['source_id']}; characters {match['start']}–{match['end']}.",
                ])
        else:
            lines.append("No wording match in this collection. Refine the search "
                         "or ask the original publisher for clarification.")
    lines.extend([
        "## Gaps and next steps",
        "- Open the original pages and check publication dates, scope and exceptions. "
        "A retrieval date is not a publication date.",
        "- Compare the full sources for agreement and disagreement before drawing a conclusion.",
        "- Record what answers your question and what is still unknown. Search excerpts "
        "can omit qualifications and do not establish completeness.",
    ])
    omitted = len(sources) - len(represented)
    if omitted:
        lines.append(f"- {omitted} collected source(s) have no selected highlight. "
                     "Their full supplied text is retained in the evidence pack.")
    lines.append(render_source_register(sources))
    return lines, {
        "highlights": highlights, "question_index": index,
        "coverage": {"sources_collected": len(sources),
                     "sources_highlighted": len(represented),
                     "excerpts_selected": len(selected)},
    }
