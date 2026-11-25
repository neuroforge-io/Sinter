"""Send verified Sinter corrections to the ERAIS experience ledger."""
from __future__ import annotations

import hashlib
import os

from . import comprehension_bridge

ENV = "SINTER_EXPERIENCE_FEEDBACK"


class ExperienceFeedbackError(ValueError):
    """The experience feedback request or response is invalid."""


class EraisExperienceFeedback:
    def __init__(self, request=None):
        self._request = request or comprehension_bridge.request

    def record(self, correction: dict, *, scope_id: str,
               source_revision: str = "unknown") -> dict:
        if not isinstance(correction, dict):
            raise ExperienceFeedbackError("correction must be an object")
        original = correction.get("original")
        replacement = correction.get("replacement")
        if not isinstance(original, str) or not isinstance(replacement, str):
            raise ExperienceFeedbackError("correction text is invalid")
        segment = str(correction.get("segment_id") or "")
        reason = str(correction.get("reason") or "")
        correction_id = "sinter:" + hashlib.sha256(
            f"{segment}:{original}:{replacement}".encode("utf-8")).hexdigest()
        response = self._request(
            comprehension_bridge.EXPERIENCE,
            method="POST",
            payload={
                "correction_id": correction_id,
                "principal": "sinter",
                "original_interpretation": original,
                "corrected_interpretation": replacement,
                "reason": reason or "human transcript review",
                "category": "recognition",
                "learning_scope": "organization",
                "scope_id": scope_id,
                "verification": "human transcript review",
                "source_revision": source_revision,
                "evidence": f"{original} -> {replacement}",
                "metadata": {"segment_id": segment,
                             "author": correction.get("author", "")},
            })
        if not isinstance(response, dict) or not isinstance(
                response.get("receipt"), dict):
            raise ExperienceFeedbackError(
                "ERAIS returned no experience receipt")
        return response["receipt"]


def from_environment():
    selected = os.environ.get(ENV, "").strip().lower()
    if selected in {"", "none", "disabled"}:
        return None
    if selected in {"erais", "canonical", "local"}:
        return EraisExperienceFeedback()
    raise ExperienceFeedbackError(f"{ENV} must select erais or disabled.")


__all__ = [
    "ENV", "EraisExperienceFeedback", "ExperienceFeedbackError",
    "from_environment",
]
