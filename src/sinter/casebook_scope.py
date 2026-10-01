"""Explicit per-question retrieval boundaries; never evidence or answer claims."""

from __future__ import annotations

import json
import re

from .evidence import literal

SCOPED_SCHEMA = "sinter-casebook/v2"
MAX_DRAFT_CHARS = 200_000
EMPTY_ANSWER = (
    "No evidence was selected for this question in the previewed context. "
    "The question remains unanswered. Review the source choices or add "
    "relevant material."
)
SURROGATE_ENCODING = "sinter-surrogate-escapes/v1"


def _invalid_unicode(value: object) -> bool:
    if isinstance(value, str):
        return any(0xD800 <= ord(char) <= 0xDFFF for char in value)
    if isinstance(value, dict):
        return any(_invalid_unicode(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return any(_invalid_unicode(item) for item in value)
    return False


def _escaped_string(value: str) -> dict:
    """Keep literal backslashes and each original surrogate code unit distinct.

    JSON string escapes alone can combine an adjacent surrogate pair on decode.
    Here doubled backslashes are literal; \\u{D800} through \\u{DFFF} encode
    one original surrogate each. All valid Unicode scalar text stays literal.
    """
    escaped = "".join(
        "\\\\"
        if char == "\\"
        else f"\\u{{{ord(char):04X}}}"
        if 0xD800 <= ord(char) <= 0xDFFF
        else char
        for char in value
    )
    return {"encoding": SURROGATE_ENCODING, "escaped_text": escaped}


def _transport_value(value):
    if isinstance(value, str):
        return _escaped_string(value) if _invalid_unicode(value) else value
    if isinstance(value, dict):
        return {key: _transport_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_transport_value(item) for item in value]
    return value


def recovered_message(message: str) -> str:
    """Only invalid error strings change; jobs must also remain UTF-8 writable."""
    if not _invalid_unicode(message):
        return message
    return (
        "The error contained invalid Unicode. Reversible escaped representation "
        f"({SURROGATE_ENCODING}): " + _escaped_string(message)["escaped_text"]
    )


def validate_response_unicode(received: dict) -> None:
    if _invalid_unicode(received):
        raise ValueError(
            "The received draft contains invalid Unicode. "
            "Its escaped representation is available for recovery."
        )


def validate_scopes(value: object, questions: list[str], source_ids: list[str]) -> list:
    """Bind sparse choices to exact question positions and canonical sources."""
    if not isinstance(value, list) or len(value) > len(questions):
        raise ValueError("Question source choices must be a bounded list.")
    known = set(source_ids)
    normalized, previous = [], -1
    for row in value:
        if not isinstance(row, dict) or set(row) != {
            "question_index",
            "question",
            "source_ids",
        }:
            raise ValueError(
                "Each question source choice needs its exact question and sources."
            )
        index = row["question_index"]
        if type(index) is not int or not previous < index < len(questions):
            raise ValueError(
                "Question source choices need unique current question positions."
            )
        if not isinstance(row["question"], str) or row["question"] != questions[index]:
            raise ValueError(
                "Questions changed or moved. Review their source choices before saving."
            )
        selected = row["source_ids"]
        if (
            not isinstance(selected, list)
            or len(selected) > len(source_ids)
            or any(not isinstance(item, str) or item not in known for item in selected)
            or len(set(selected)) != len(selected)
        ):
            raise ValueError(
                "Choose unique existing sources for each question; "
                "review removed sources."
            )
        normalized.append(
            {
                "question_index": index,
                "question": questions[index],
                "source_ids": list(selected),
            }
        )
        previous = index
    return normalized


def draft_context(report: dict) -> dict:
    """Match the displayed bounded packet; scopes never admit other questions' hits."""
    if not report.get("question_scopes"):
        return {
            "questions": [row["question"] for row in report["question_index"]][:8],
            "excerpts": [
                {"id": row["id"], "text": row["quote"]}
                for row in report.get("excerpts", [])[:8]
            ],
        }
    all_questions = report["question_index"]
    source_ids = [row["id"] for row in report["source_register"]]
    scopes = validate_scopes(
        report["question_scopes"],
        [row["question"] for row in all_questions],
        source_ids,
    )
    by_index = {row["question_index"]: row["source_ids"] for row in scopes}
    originals = {row["id"]: row for row in report.get("excerpts", [])}
    selected_questions, allowed_hits = [], set()
    for index, row in enumerate(all_questions[:8]):
        allowed_sources = by_index.get(index, source_ids)
        for identity in row["excerpt_ids"]:
            if (
                identity not in originals
                or originals[identity]["source_id"] not in allowed_sources
            ):
                raise ValueError(
                    "A selected passage falls outside its question source choice."
                )
        allowed_hits.update(row["excerpt_ids"])
        selected_questions.append(
            {
                "question_index": index,
                "question": row["question"],
                "source_ids": list(allowed_sources),
                "excerpt_ids": list(row["excerpt_ids"]),
            }
        )
    selected = [row for row in report.get("excerpts", []) if row["id"] in allowed_hits][
        :8
    ]
    sent = {row["id"] for row in selected}
    for row in selected_questions:
        row["excerpt_ids"] = [
            identity for identity in row["excerpt_ids"] if identity in sent
        ]
    return {
        "questions": selected_questions,
        "excerpts": [
            {"id": row["id"], "source_id": row["source_id"], "text": row["quote"]}
            for row in selected
        ],
    }


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("The scoped draft contains duplicate JSON fields.")
        result[key] = value
    return result


def _finite_json(value):
    raise ValueError("The scoped draft contains an invalid JSON number.")


def scoped_draft(content: str, packet: dict) -> str:
    """Admit complete ordered sections and each section's own references only.

    This validates identity and placement, not whether a claim is supported.
    A zero-evidence question is rendered with a fixed unanswered notice.
    """
    if not isinstance(content, str) or not 0 < len(content) <= MAX_DRAFT_CHARS:
        raise ValueError("The scoped draft exceeds its response admission bound.")
    try:
        data = json.loads(
            content, object_pairs_hook=_unique_object, parse_constant=_finite_json
        )
    except (json.JSONDecodeError, RecursionError) as exc:
        raise ValueError("The scoped draft is not a complete JSON response.") from exc
    if not isinstance(data, dict) or set(data) != {"sections"}:
        raise ValueError("The scoped draft needs only its ordered question sections.")
    rows, questions = data["sections"], packet["questions"]
    if not isinstance(rows, list) or len(rows) != len(questions):
        raise ValueError("The scoped draft must cover every previewed question once.")
    output = [
        "**UNVERIFIED MODEL DRAFT — check every claim against the original wording.**",
        "These sections cover only the previewed questions and their own selected "
        "passages. Valid reference IDs do not establish factual support.",
    ]
    for index, (row, expected) in enumerate(zip(rows, questions)):
        if (
            not isinstance(row, dict)
            or set(row) != {"question_index", "question", "text"}
            or type(row["question_index"]) is not int
            or row["question_index"] != index
            or row["question"] != expected["question"]
            or not isinstance(row["text"], str)
            or "\x00" in row["text"]
            or any(0xD800 <= ord(char) <= 0xDFFF for char in row["text"])
        ):
            raise ValueError(
                "The scoped draft changed or reordered a question section."
            )
        text = row["text"]
        allowed = set(expected["excerpt_ids"])
        if not allowed:
            if text != "":
                raise ValueError("A zero-evidence question must remain unanswered.")
            text = EMPTY_ANSWER
        else:
            cites = set(re.findall(r"\[([ES][^\]\r\n]*)\]", text))
            raw_ids = set(re.findall(r"(?<![\w])[ES][0-9a-f]{24}(?![\w])", text))
            if not text.strip() or not cites or not (cites | raw_ids) <= allowed:
                raise ValueError(
                    "A scoped question used an unknown or another question's reference."
                )
            if re.search(
                r"\[(?:to confirm|recipient|name|organisation|organization|"
                r"sender[^\]]*|contact details|insert[^\]]*|add[^\]]*)\]",
                text,
                re.I,
            ):
                raise ValueError("The scoped draft left unfinished placeholders.")
        output += [f"## Question {index + 1}: {literal(expected['question'])}", text]
    return "\n\n".join(output)


def recovered_draft(report: dict, received: dict | None, message: str) -> dict:
    """Keep received text, or the absence of text, without inventing an outcome."""
    raw = received["content"] if received is not None else ""
    content_escaped = _invalid_unicode(raw)
    shown = _escaped_string(raw)["escaped_text"] if content_escaped else raw
    safe_received = _transport_value(received)
    safe_message = recovered_message(message)
    fence = "`" * max(3, max((len(s) for s in re.findall(r"`+", shown)), default=0) + 1)
    display = (
        "**INCOMPLETE MODEL DRAFT — "
        + (
            "review the partial text."
            if received is not None
            else "no admitted answer."
        )
        + "**\n\nThe optional draft did not produce an admitted answer. "
        + (
            (
                "The received content contains invalid Unicode. The text below is a "
                "reversible escaped representation, not verbatim Unicode text. "
                f"Format {SURROGATE_ENCODING}: doubled backslashes are literal; "
                "\\u{D800} through \\u{DFFF} retain each original surrogate code unit. "
                if content_escaped
                else "It is retained verbatim below for local recovery; "
            )
            + "These are not "
            "accepted question answers. "
            if received is not None
            else "No response text was made available to this workflow. If contact was "
            "interrupted, the remote request may still have been processed. "
        )
        + "The original "
        "source-only report and evidence remain unchanged. No request was replayed.\n\n"
        + (
            "Invalid Unicode in response or error metadata is retained as labelled "
            "escaped values in the evidence JSON.\n\n"
            if _invalid_unicode(received) or _invalid_unicode(message)
            else ""
        )
        + (fence + "text\n" + shown + "\n" + fence if received is not None else "")
    )
    return {
        **report,
        "model_draft": True,
        "incomplete": True,
        "document_markdown": display,
        "source_document_markdown": report.get("document_markdown", ""),
        "markdown": display + "\n\n---\n\n" + report["markdown"],
        "scoped_model_response": safe_received,
        "generation_error": {
            "message": safe_message,
            **(
                {"original_message": _escaped_string(message)}
                if _invalid_unicode(message)
                else {}
            ),
        },
        "warnings": [
            safe_message,
            "The received scoped draft was withheld, not validated."
            if received is not None
            else "No response text was available; no question answers were admitted.",
        ]
        + report["warnings"],
    }
