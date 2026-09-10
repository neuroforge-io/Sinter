"""CLI entry point — `sinter` command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import __version__


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(
        prog="sinter",
        description="Sinter — chat, code review, research, and custom workflows via the NeuroForge Fracture API.",
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )

    sub = parser.add_subparsers(dest="command", help="Available commands")

    # serve
    srv = sub.add_parser("serve", help="Launch web GUI")
    srv.add_argument("-p", "--port", type=int, default=8420)
    srv.add_argument("--host", default="127.0.0.1")
    srv.add_argument("--no-browser", action="store_true")

    # chat
    ch = sub.add_parser("chat", help="Interactive chat")
    ch.add_argument("-m", "--message", help="Single message (non-interactive)")
    ch.add_argument("-s", "--system", default="", help="System prompt")
    ch.add_argument("--max-tokens", type=int, default=512)

    # review
    rv = sub.add_parser("review", help="Multi-pass code review")
    rv.add_argument("file", help="Source file to review")
    rv.add_argument("-l", "--language", default="Python")
    rv.add_argument("-o", "--output")
    rv.add_argument("--no-stream", action="store_true")

    # research
    rs = sub.add_parser("research", help="Research a topic")
    rs.add_argument("topic")
    rs.add_argument("-o", "--output")
    rs.add_argument("--no-stream", action="store_true")

    # template
    tp = sub.add_parser("template", help="Run a template")
    tp.add_argument("name", help="Template name")
    tp.add_argument(
        "-v", "--var", action="append", default=[], metavar="KEY=VALUE"
    )
    tp.add_argument("-o", "--output")
    tp.add_argument("--no-stream", action="store_true")

    # templates
    sub.add_parser("templates", help="List available templates")

    # health
    sub.add_parser("health", help="Check API connectivity")

    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return

    dispatch = {
        "health": _cmd_health,
        "chat": _cmd_chat,
        "review": _cmd_review,
        "research": _cmd_research,
        "templates": _cmd_templates,
        "template": _cmd_template,
        "serve": _cmd_serve,
    }
    dispatch[args.command](args)


def _cmd_health(args=None) -> None:
    from .client import health_check
    ok, msg = health_check()
    print(f"{'OK' if ok else 'FAIL'}: {msg}")
    sys.exit(0 if ok else 1)


def _cmd_chat(args) -> None:
    from .client import Message, chat, chat_stream

    messages: list[Message] = []
    if args.system:
        messages.append(Message(role="system", content=args.system))

    if args.message:
        # Single-message mode: send one message, print response, exit.
        messages.append(Message(role="user", content=args.message))
        for token in chat_stream(messages, max_tokens=args.max_tokens):
            print(token, end="", flush=True)
        print()
        return

    # Interactive mode
    print("Sinter Chat (type 'quit' to exit, 'clear' to reset)")
    print("-" * 50)
    while True:
        try:
            user_input = input("You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if user_input.lower() in ("quit", "exit", "q"):
            break
        if user_input.lower() == "clear":
            messages = [m for m in messages if m.role == "system"]
            print("[conversation cleared]")
            continue
        if not user_input:
            continue

        messages.append(Message(role="user", content=user_input))
        print("AI: ", end="", flush=True)
        full = []
        for token in chat_stream(messages, max_tokens=args.max_tokens):
            print(token, end="", flush=True)
            full.append(token)
        print()
        messages.append(Message(role="assistant", content="".join(full)))


def _cmd_review(args) -> None:
    from .templates import get_builtin_template, render_prompt
    from .client import Message, chat, chat_stream

    source = Path(args.file).read_text(errors="replace")
    filename = Path(args.file).name
    print(f"Reviewing: {filename} ({len(source)} bytes)")
    print("=" * 60)

    template = get_builtin_template("code-review")
    variables = {"code": source, "language": args.language}
    results: list[str] = []

    for i, step in enumerate(template.steps):
        print(f"\n[{i+1}/{len(template.steps)}] {step.name}...")
        prompt = render_prompt(step.prompt, variables)
        messages = [Message(role="user", content=prompt)]

        if step.stream and not args.no_stream:
            full = []
            for token in chat_stream(messages, max_tokens=step.max_tokens):
                print(token, end="", flush=True)
                full.append(token)
            print()
            content = "".join(full)
        else:
            result = chat(messages, max_tokens=step.max_tokens)
            content = result.content
            print(content)

        results.append(content)
        variables["previous"] = "\n\n".join(results)

    out = args.output or str(Path(args.file).with_suffix(".review.md"))
    report = f"# Code Review: {filename}\n\n"
    for i, step in enumerate(template.steps):
        report += f"## Pass {i+1} — {step.name}\n\n{results[i]}\n\n"

    Path(out).write_text(report)
    print(f"\n{'=' * 60}")
    print(f"Report saved: {out}")


def _cmd_research(args) -> None:
    from .templates import get_builtin_template, render_prompt
    from .client import Message, chat, chat_stream

    template = get_builtin_template("research")
    variables = {"topic": args.topic}
    results: list[str] = []

    print(f"Research: {args.topic}")
    print("=" * 60)

    for i, step in enumerate(template.steps):
        print(f"\n[{i+1}/{len(template.steps)}] {step.name}...")
        prompt = render_prompt(step.prompt, variables)
        messages = [Message(role="user", content=prompt)]

        if step.stream and not args.no_stream:
            full = []
            for token in chat_stream(messages, max_tokens=step.max_tokens):
                print(token, end="", flush=True)
                full.append(token)
            print()
            content = "".join(full)
        else:
            result = chat(messages, max_tokens=step.max_tokens)
            content = result.content
            print(content)

        results.append(content)
        variables["previous"] = "\n\n".join(results)

    out = args.output or "research_output.md"
    report = f"# Research: {args.topic}\n\n"
    for i, step in enumerate(template.steps):
        report += f"## {step.name}\n\n{results[i]}\n\n"

    Path(out).write_text(report)
    print(f"\nReport saved: {out}")


def _cmd_templates(args=None) -> None:
    from .templates import get_builtin_template, list_builtin_templates

    print("Available templates:")
    print("-" * 50)
    for name in list_builtin_templates():
        t = get_builtin_template(name)
        vars_str = ", ".join(t.variables) if t.variables else "(none)"
        print(f"  {name:15s}  {t.description}")
        print(f"  {'':15s}  Variables: {vars_str}")
        print()


def _cmd_template(args) -> None:
    from .templates import get_builtin_template, render_prompt
    from .client import Message, chat_stream, chat as api_chat

    template = get_builtin_template(args.name)
    variables = {}
    for v in args.var:
        k, _, val = v.partition("=")
        variables[k] = val

    missing = [v for v in template.variables if v not in variables and v != "previous"]
    if missing:
        print(f"Missing variables: {', '.join(missing)}")
        print(
            f"Usage: sinter template {args.name} "
            + " ".join(f"-v {v}=VALUE" for v in template.variables if v != "previous")
        )
        sys.exit(1)

    results: list[str] = []
    print(f"Running: {template.name}")
    print("=" * 60)

    for i, step in enumerate(template.steps):
        print(f"\n[{i+1}/{len(template.steps)}] {step.name}...")
        prompt = render_prompt(step.prompt, variables)
        messages = [Message(role="user", content=prompt)]

        if step.stream and not args.no_stream:
            full = []
            for token in chat_stream(messages, max_tokens=step.max_tokens):
                print(token, end="", flush=True)
                full.append(token)
            print()
            content = "".join(full)
        else:
            result = api_chat(messages, max_tokens=step.max_tokens)
            content = result.content
            print(content)

        results.append(content)
        variables["previous"] = "\n\n".join(results)

    if args.output:
        Path(args.output).write_text("\n\n---\n\n".join(results))
        print(f"\nSaved: {args.output}")


def _cmd_serve(args) -> None:
    from .server import serve
    serve(host=args.host, port=args.port, open_browser=not args.no_browser)


if __name__ == "__main__":
    main()
