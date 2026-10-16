"""Recognize a bounded affirmative review result, never a quoted claim of one."""
from __future__ import annotations

import re

# A label may describe the review, but arbitrary text before a clean phrase can
# negate it or turn it into an example. Keep the admitted label grammar closed.
_LABEL = re.compile(
    r"(?i)^(?:(?:unverified\s+)?(?:(?:fictional|first|remaining)\s+)?"
    r"(?:review|commentary|assessment|conclusion|result|status)(?:\s+result)?"
    r"|(?:explicit\s+)?retry)\s*:\s*"
)
_CLEAN = re.compile(
    r"(?i)^(?:no (?:issues?|problems?|mistakes?|errors?|bugs?) (?:found|detected|noted)"
    r"|no (?:demonstrated|confirmed|substantiated) (?:issues?|problems?|errors?|bugs?)"
    r"|(?:nothing|no issues?) (?:was |is |were )?demonstrated"
    r"|all checks? (?:passed|ok)|nothing (?:wrong|found|to report))\b"
)
_SCOPE = re.compile(
    r"(?i)^(?:after (?:checking|reviewing|examining|inspecting)\s+"
    r"|(?:in|within|for|with) (?:the|this|these|supplied|provided)\s+)"
    r"[^!?\n]+$"
)
_CHECKED = re.compile(
    r"(?i)^(?:I|we) (?:checked|reviewed|examined|inspected)\s+[^!?\n]+$"
)
# These words cannot supply the free-form scope of an affirmative result. This
# guard applies only to the clean-result shortcut, not to grounded findings.
_QUALIFIED_SCOPE = re.compile(
    r"(?i)\b(?:if|unless|would|could|should|might|may|not|never|cannot|can't|"
    r"but|however|except|although|though|providing|assuming|"
    r"unable|unavailable|incomplete|hypothetical\w*|example|template|phrase|"
    r"wording|label|claim\w*|assertion\w*|say|says|saying|said|write|written|"
    r"expected|expectation|means|meaning|sentence|incorrect|inaccurate|"
    r"misleading|false|withdraw\w*)\b"
    r"|\bprovided\s+(?:that|all|there|it|the)\b|\bsubject\s+to\b"
    r"|[;:—–]|\s-\s|\b\w+n['’]t\b"
)


def explicit_clean_result(paragraph: str) -> bool:
    """Admit an affirmative result and optional completed-review scope only.

    Unknown prose falls through to the existing source-grounding gate. A phrase
    inside a quotation, code block, condition or discussion of wording is not
    itself a review result. This recognizes a result, not its truth or coverage.
    """
    value = paragraph.strip()
    if not value or value.startswith(('>', '`', '~')):
        return False
    value = re.sub(r"^(?:[-*] |\d+[.)] )", "", value)
    # Bold emphasis is presentation; inline code and quotation remain data.
    value = re.sub(r"\*\*([^*\n]+)\*\*", r"\1", value)
    value = _LABEL.sub("", value, count=1)
    sentences = re.split(r"(?<=[.!?])\s+|\n+", value)
    if '?' in sentences[0]:
        return False
    first = sentences[0].rstrip('.!').strip()
    match = _CLEAN.match(first)
    if match is None:
        return False
    scope = first[match.end():].strip()
    if scope and (not _SCOPE.fullmatch(scope) or _QUALIFIED_SCOPE.search(scope)):
        return False
    # A later condition or withdrawal must not borrow the earlier clean words.
    # Completed checks are allowed; arbitrary later prose needs grounding.
    for sentence in sentences[1:]:
        if '?' in sentence:
            return False
        sentence = sentence.rstrip('.!').strip()
        if sentence and (not _CHECKED.fullmatch(sentence)
                         or _QUALIFIED_SCOPE.search(sentence)):
            return False
    return True


def clean_result_prose(content: str) -> str:
    """Exclude Markdown code, including blank-separated and unclosed fences.

    Only clean-result admission uses this view. Original commentary and quoted
    source evidence stay unchanged for the existing grounded-finding checks.
    """
    result = []
    marker = ''
    width = 0
    for line in content.splitlines():
        fence = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)$", line)
        if marker:
            if (fence and fence[1][0] == marker and len(fence[1]) >= width
                    and not fence[2].strip()):
                marker = ''
            result.append('')
        elif fence:
            marker, width = fence[1][0], len(fence[1])
            result.append('')
        elif line.startswith(('    ', '\t')):
            result.append('')
        else:
            result.append(line)
    return '\n'.join(result)
