"""Template engine — define, load, and run multi-step workflows."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from .client import Message, chat, chat_stream, search, ChatResult

log = logging.getLogger(__name__)


@dataclass
class Step:
    name: str
    prompt: str
    role: str = "user"
    max_tokens: int = 512
    use_search: bool = False
    search_field: str = "topic"
    stream: bool = False


@dataclass
class Template:
    name: str
    description: str
    steps: list[Step] = field(default_factory=list)
    variables: list[str] = field(default_factory=list)
    source: str = ""  # "builtin" | file path


def render_prompt(template_str: str, variables: dict[str, str]) -> str:
    result = template_str
    for k, v in variables.items():
        result = result.replace("{{" + k + "}}", v)
    return result


def list_builtin_templates() -> list[str]:
    return ["chat", "code-review", "research", "summarize", "explain", "custom"]


def get_builtin_template(name: str) -> Template:
    templates = {
        "chat": Template(
            name="Chat",
            description="Simple freeform chat with optional system prompt.",
            variables=["message", "system"],
            source="builtin",
            steps=[
                Step(
                    name="Chat",
                    prompt="{{message}}",
                    role="user",
                    max_tokens=512,
                    stream=True,
                ),
            ],
        ),
        "code-review": Template(
            name="Code Review",
            description="Multi-pass code review: identify issues, suggest fixes, summarize.",
            variables=["code", "language"],
            source="builtin",
            steps=[
                Step(
                    name="Identify Issues",
                    prompt=(
                        "Review this {{language}} code. List specific issues "
                        "with line references. Group as: BUGS, SECURITY, "
                        "ERROR HANDLING, STYLE.\n\n```{{language}}\n{{code}}\n```"
                    ),
                    max_tokens=512,
                ),
                Step(
                    name="Suggest Fixes",
                    prompt=(
                        "For each issue above, provide a concrete fix: "
                        "show the corrected code snippet. "
                        "If minor, say 'skip' and explain why."
                    ),
                    max_tokens=512,
                    stream=True,
                ),
                Step(
                    name="Summary",
                    prompt=(
                        "Write a 1-paragraph executive summary: "
                        "how many issues, severity distribution, "
                        "and the single most important thing to fix first."
                    ),
                    max_tokens=256,
                ),
            ],
        ),
        "research": Template(
            name="Research",
            description="Research a topic: outline key points, expand details, generate action items.",
            variables=["topic"],
            source="builtin",
            steps=[
                Step(
                    name="Outline",
                    prompt=(
                        "Outline 5 key points about {{topic}}. "
                        "For each: a title, one-sentence description, "
                        "and a concrete example or data point."
                    ),
                    max_tokens=512,
                ),
                Step(
                    name="Expand",
                    prompt=(
                        "For each of these points:\n\n{{previous}}\n\n"
                        "Expand into a short paragraph (2-3 sentences) "
                        "explaining when and why this matters in practice."
                    ),
                    max_tokens=512,
                    stream=True,
                ),
                Step(
                    name="Action Items",
                    prompt=(
                        "Based on the above:\n\n{{previous}}\n\n"
                        "Give 3 concrete action items: what to try first, "
                        "what to adopt next, and what to plan long-term."
                    ),
                    max_tokens=256,
                ),
            ],
        ),
        "summarize": Template(
            name="Summarize",
            description="Summarize text in a specified format.",
            variables=["text", "format"],
            source="builtin",
            steps=[
                Step(
                    name="Summarize",
                    prompt=(
                        "Summarize the following in {{format}} format:\n\n{{text}}"
                    ),
                    max_tokens=512,
                    stream=True,
                ),
            ],
        ),
        "explain": Template(
            name="Explain",
            description="Explain a concept at a given level with an analogy.",
            variables=["concept", "level"],
            source="builtin",
            steps=[
                Step(
                    name="Explain",
                    prompt=(
                        "Explain {{concept}} at a {{level}} level. "
                        "Use an analogy. Be concise."
                    ),
                    max_tokens=256,
                    stream=True,
                ),
            ],
        ),
        "custom": Template(
            name="Custom",
            description="Write your own single-step prompt.",
            variables=["prompt"],
            source="builtin",
            steps=[
                Step(
                    name="Custom",
                    prompt="{{prompt}}",
                    max_tokens=512,
                    stream=True,
                ),
            ],
        ),
    }
    return templates.get(name, templates["custom"])


def load_template_file(path: str | Path) -> Template:
    p = Path(path)
    text = p.read_text()

    if p.suffix in (".yaml", ".yml"):
        return _parse_yaml(text, p.stem)
    else:
        data = json.loads(text)
        return Template(
            name=data.get("name", p.stem),
            description=data.get("description", ""),
            source=str(p),
            steps=[
                Step(
                    name=s["name"],
                    prompt=s["prompt"],
                    role=s.get("role", "user"),
                    max_tokens=s.get("max_tokens", 512),
                    use_search=s.get("use_search", False),
                    search_field=s.get("search_field", "topic"),
                    stream=s.get("stream", False),
                )
                for s in data.get("steps", [])
            ],
            variables=data.get("variables", []),
        )


def _parse_yaml(text: str, name: str) -> Template:
    steps: list[Step] = []
    variables: list[str] = []
    description = ""
    template_name = name
    current_step: dict = {}
    in_steps = False

    for line in text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue

        if not line.startswith(" ") and ":" in stripped:
            k, v = stripped.split(":", 1)
            k, v = k.strip(), v.strip()
            if k == "name":
                template_name = v
            elif k == "description":
                description = v
            elif k == "steps":
                in_steps = True
            elif k == "variables":
                in_steps = False
            continue

        if in_steps and stripped.startswith("- name:"):
            if current_step:
                steps.append(_dict_to_step(current_step))
            current_step = {"name": stripped.split(":", 1)[1].strip()}
        elif in_steps and ":" in stripped:
            k, v = stripped.split(":", 1)
            k, v = k.strip(), v.strip()
            if k == "use_search":
                current_step[k] = v.lower() in ("true", "yes", "1")
            elif k == "max_tokens":
                try:
                    current_step[k] = int(v)
                except ValueError:
                    current_step[k] = 512
            elif k == "stream":
                current_step[k] = v.lower() in ("true", "yes", "1")
            else:
                current_step[k] = v
        elif not in_steps and stripped.startswith("- "):
            variables.append(stripped[2:].strip())

    if current_step:
        steps.append(_dict_to_step(current_step))

    return Template(
        name=template_name,
        description=description,
        steps=steps,
        variables=variables,
        source="file",
    )


def _dict_to_step(d: dict) -> Step:
    return Step(
        name=d.get("name", "step"),
        prompt=d.get("prompt", ""),
        role=d.get("role", "user"),
        max_tokens=d.get("max_tokens", 512),
        use_search=d.get("use_search", False),
        search_field=d.get("search_field", "topic"),
        stream=d.get("stream", False),
    )


def run_template(
    template: Template,
    variables: dict[str, str],
    on_step=None,
    on_token=None,
) -> list[ChatResult]:
    history: list[Message] = []
    results: list[ChatResult] = []

    for i, step in enumerate(template.steps):
        if on_step:
            on_step(step.name, i + 1, len(template.steps))

        prompt = render_prompt(step.prompt, variables)

        if step.use_search:
            query = variables.get(step.search_field, "")
            if query:
                try:
                    sr = search(query)
                    if sr.results:
                        snippets = "\n".join(
                            f"[{j+1}] {r.title}: {r.content[:300]}"
                            for j, r in enumerate(sr.results[:3])
                        )
                        prompt += f"\n\nWeb search results:\n{snippets}"
                except Exception as exc:
                    log.warning("Search failed for %r: %s", query, exc)

        step_messages = list(history) + [Message(role=step.role, content=prompt)]

        if step.stream and on_token:
            full = []
            for token in chat_stream(step_messages, max_tokens=step.max_tokens):
                full.append(token)
                on_token(token)
            content = "".join(full)
            result = ChatResult(content=content, finish_reason="stop")
        else:
            result = chat(step_messages, max_tokens=step.max_tokens)
            content = result.content

        results.append(result)
        history.append(Message(role=step.role, content=prompt))
        history.append(Message(role="assistant", content=content))
        variables["previous"] = "\n\n".join(r.content for r in results)

    return results
