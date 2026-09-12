"""Collect template events without losing useful work when a later step fails."""
from __future__ import annotations

from .client import APIError
from .templates import Template, TemplateStepError, template_events


class TemplateRunError(APIError):
    """A failed run with explicitly incomplete, recoverable output."""

    def __init__(self, cause: APIError | ValueError, result: dict):
        super().__init__(str(cause), getattr(cause, "status", 400))
        self.partial_result = result


def collect_run(template: Template, variables: dict, progress=lambda message: None) -> dict:
    """Run once; preserve completed steps and label the stopped step incomplete."""
    result = {"results": [], "sources": [], "complete": False}
    try:
        for event in template_events(template, variables, stream=False):
            if event["type"] == "step":
                progress(event["name"])
            elif event["type"] == "step_done":
                result["results"].append(event)
            elif event["type"] == "sources":
                result["sources"].append(event)
            elif event["type"] == "step_partial":
                result["partial"] = event
    except (APIError, ValueError) as exc:
        if isinstance(exc, TemplateStepError):
            result["partial"] = exc.partial
        result["error"] = str(exc)
        raise TemplateRunError(exc, result) from exc
    result["complete"] = True
    return result
