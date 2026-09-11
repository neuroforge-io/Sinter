"""Compatibility tests for the public Sinter toolkit."""
import re
from pathlib import Path
from unittest.mock import patch

import pytest

from sinter import __version__
from sinter.client import Message, ChatResult, SearchResult, SearchResponse
from sinter.templates import Step, render_prompt, get_builtin_template, list_builtin_templates, _parse_yaml


def test_version():
    assert re.fullmatch(r'\d+\.\d+\.\d+', __version__)
    assert f'version = "{__version__}"' in (Path(__file__).parents[1]/'pyproject.toml').read_text(encoding='utf-8')


def test_message():
    m = Message(role="user", content="hello")
    assert m.role == "user" and m.content == "hello"


def test_chat_result():
    r = ChatResult(content="hi", total_tokens=10)
    assert r.content == "hi" and r.finish_reason == ""


def test_search_result():
    assert SearchResult(title="t", url="http://x", content="c").title == "t"


def test_search_response():
    sp = SearchResponse(retrieved_at="2026-01-01", results=[])
    assert sp.results == []


def test_render_prompt():
    assert render_prompt("Hello {{name}}, you are {{age}}.", {"name": "Alice", "age": "30"}) == "Hello Alice, you are 30."


def test_render_prompt_no_vars():
    assert render_prompt("static text", {}) == "static text"


def test_render_prompt_multiple_same_var():
    assert render_prompt("{{x}} and {{x}}", {"x": "Y"}) == "Y and Y"


def test_list_builtin_templates():
    assert {"chat", "code-review", "research", "summarize", "explain", "custom"} <= set(list_builtin_templates())


def test_get_builtin_chat():
    t = get_builtin_template("chat")
    assert t.name == "Chat" and len(t.steps) == 1 and "message" in t.variables


def test_get_builtin_code_review():
    t = get_builtin_template("code-review")
    assert len(t.steps) == 3 and t.steps[0].name == "Identify Issues" and t.steps[2].stream is False


def test_get_builtin_research():
    t = get_builtin_template("research")
    assert len(t.steps) == 3 and t.steps[1].stream is True


def test_get_builtin_unknown_falls_back():
    assert get_builtin_template("nonexistent").name == "Custom"


def test_step_defaults():
    s = Step(name="test", prompt="hi")
    assert s.role == "user" and s.max_tokens == 512 and s.use_search is False and s.stream is False


def test_parse_yaml():
    source = '''
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
'''
    t = _parse_yaml(source, "test")
    assert t.name == "Test Template" and t.description == "A test."
    assert t.variables == ["input", "style"] and len(t.steps) == 2
    assert t.steps[0].name == "Step One" and t.steps[0].max_tokens == 256 and t.steps[1].stream is True


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
    assert "code-review" in out and "research" in out


def test_cli_no_command(capsys):
    from sinter.cli import main
    main([])
    out = capsys.readouterr().out
    assert "usage" in out.lower() or "sinter" in out.lower()


def test_client_chat_mock():
    response = {"choices": [{"message": {"role": "assistant", "content": "Hello!"}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12}}
    with patch("sinter.client._post", return_value=response):
        from sinter.client import chat
        result = chat([Message(role="user", content="hi")])
        assert result.content == "Hello!" and result.total_tokens == 12 and result.finish_reason == "stop"


def test_client_list_models_mock():
    response = {"data": [{"id": "erais-fracture-gemma", "object": "model", "created": 0, "owned_by": "neuroforge"}]}
    with patch("sinter.client._get", return_value=response):
        from sinter.client import list_models
        models = list_models()
        assert len(models) == 1 and models[0]["id"] == "erais-fracture-gemma"


def test_client_search_mock():
    response = {"retrieved_at": "2026-01-01T00:00:00Z", "results": [{"title": "Test", "url": "http://x", "content": "body"}]}
    with patch("sinter.client._post", return_value=response):
        from sinter.client import search
        result = search("test query")
        assert len(result.results) == 1 and result.results[0].title == "Test"


def test_run_template_mock():
    result = ChatResult(content="output text", total_tokens=50, finish_reason="stop")
    with patch("sinter.templates.chat", return_value=result):
        from sinter.templates import run_template
        results = run_template(get_builtin_template("custom"), {"prompt": "test prompt"})
        assert len(results) == 1 and results[0].content == "output text"
