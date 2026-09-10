"""Tests for the Sinter toolkit."""

import json
import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from sinter import __version__
from sinter.client import Message, ChatResult, SearchResult, SearchResponse
from sinter.templates import (
    Template, Step, render_prompt, get_builtin_template,
    list_builtin_templates, load_template_file, _parse_yaml,
)


# ── Version ──────────────────────────────────────────────

def test_version():
    assert __version__ == "0.1.0"


# ── Message / Data classes ───────────────────────────────

def test_message():
    m = Message(role="user", content="hello")
    assert m.role == "user"
    assert m.content == "hello"


def test_chat_result():
    r = ChatResult(content="hi", total_tokens=10)
    assert r.content == "hi"
    assert r.finish_reason == ""


def test_search_result():
    sr = SearchResult(title="t", url="http://x", content="c")
    assert sr.title == "t"


def test_search_response():
    sp = SearchResponse(retrieved_at="2026-01-01", results=[])
    assert sp.results == []


# ── Render prompt ────────────────────────────────────────

def test_render_prompt():
    result = render_prompt("Hello {{name}}, you are {{age}}.", {"name": "Alice", "age": "30"})
    assert result == "Hello Alice, you are 30."


def test_render_prompt_no_vars():
    assert render_prompt("static text", {}) == "static text"


def test_render_prompt_multiple_same_var():
    result = render_prompt("{{x}} and {{x}}", {"x": "Y"})
    assert result == "Y and Y"


# ── Templates ────────────────────────────────────────────

def test_list_builtin_templates():
    names = list_builtin_templates()
    assert "chat" in names
    assert "code-review" in names
    assert "research" in names
    assert "summarize" in names
    assert "explain" in names
    assert "custom" in names


def test_get_builtin_chat():
    t = get_builtin_template("chat")
    assert t.name == "Chat"
    assert len(t.steps) == 1
    assert "message" in t.variables


def test_get_builtin_code_review():
    t = get_builtin_template("code-review")
    assert len(t.steps) == 3
    assert t.steps[0].name == "Identify Issues"
    assert t.steps[2].stream is False


def test_get_builtin_research():
    t = get_builtin_template("research")
    assert len(t.steps) == 3
    assert t.steps[1].stream is True


def test_get_builtin_unknown_falls_back():
    t = get_builtin_template("nonexistent")
    assert t.name == "Custom"


def test_step_defaults():
    s = Step(name="test", prompt="hi")
    assert s.role == "user"
    assert s.max_tokens == 512
    assert s.use_search is False
    assert s.stream is False


# ── YAML parsing ─────────────────────────────────────────

def test_parse_yaml():
    yaml_text = """
name: Test Template
description: A test.
variables:
  - input
  - style
steps:
  - name: Step One
    prompt: "Process {{input}} in {{style}} style."
    max_tokens: 256
  - name: Step Two
    prompt: "Summarize."
    stream: true
"""
    t = _parse_yaml(yaml_text, "test")
    assert t.name == "Test Template"
    assert t.description == "A test."
    assert t.variables == ["input", "style"]
    assert len(t.steps) == 2
    assert t.steps[0].name == "Step One"
    assert t.steps[0].max_tokens == 256
    assert t.steps[1].stream is True


# ── CLI ──────────────────────────────────────────────────

def test_cli_help(capsys):
    from sinter.cli import main
    with pytest.raises(SystemExit) as exc:
        main(["--help"])
    assert exc.value.code == 0


def test_cli_version(capsys):
    from sinter.cli import main
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0


def test_cli_templates(capsys):
    from sinter.cli import main
    main(["templates"])
    out = capsys.readouterr().out
    assert "code-review" in out
    assert "research" in out


def test_cli_no_command(capsys):
    from sinter.cli import main
    main([])
    out = capsys.readouterr().out
    assert "usage" in out.lower() or "sinter" in out.lower()


# ── Client mocking ───────────────────────────────────────

def test_client_chat_mock():
    mock_response = {
        "choices": [{"message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
    }
    with patch("sinter.client._post", return_value=mock_response):
        from sinter.client import chat
        result = chat([Message(role="user", content="hi")])
        assert result.content == "Hello!"
        assert result.total_tokens == 12
        assert result.finish_reason == "stop"


def test_client_list_models_mock():
    mock = {"data": [{"id": "erais-fracture-gemma", "object": "model", "created": 0, "owned_by": "neuroforge"}]}
    with patch("sinter.client._get", return_value=mock):
        from sinter.client import list_models
        models = list_models()
        assert len(models) == 1
        assert models[0]["id"] == "erais-fracture-gemma"


def test_client_search_mock():
    mock = {
        "retrieved_at": "2026-01-01T00:00:00Z",
        "results": [{"title": "Test", "url": "http://x", "content": "body"}],
    }
    with patch("sinter.client._post", return_value=mock):
        from sinter.client import search
        result = search("test query")
        assert len(result.results) == 1
        assert result.results[0].title == "Test"


# ── Template run (mocked) ────────────────────────────────

def test_run_template_mock():
    mock_result = ChatResult(content="output text", total_tokens=50, finish_reason="stop")
    with patch("sinter.templates.chat", return_value=mock_result):
        from sinter.templates import run_template
        t = get_builtin_template("custom")
        results = run_template(t, {"prompt": "test prompt"})
        assert len(results) == 1
        assert results[0].content == "output text"
