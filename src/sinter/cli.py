"""Portable command line, modified for Sinter 0.2 to share workflow services."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__, client


def _write(path: str, content: str) -> None:
    Path(path).write_text(content, encoding="utf-8")
    print(f"Saved: {path}")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(prog="sinter", description="Sinter - source-linked community work and the Fracture API")
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = parser.add_subparsers(dest="command")
    server = sub.add_parser("serve", help="Open the local web workbench")
    server.add_argument("-p", "--port", type=int, default=8420)
    server.add_argument("--host", default="127.0.0.1")
    server.add_argument("--no-browser", action="store_true")
    chat = sub.add_parser("chat", help="Generative chat (not verified)")
    chat.add_argument("-m", "--message")
    chat.add_argument("-s", "--system", default="")
    chat.add_argument("--max-tokens", type=int, default=512)
    review = sub.add_parser("review", help="Bounded text collection review with explicit coverage")
    review.add_argument("file")
    review.add_argument("-l", "--language", default="", help="Optional language hint for the review; part of checkpoint identity")
    review.add_argument("-o", "--output")
    review.add_argument("--no-stream", action="store_true", help="Compatibility flag; bounded batches use JSON responses")
    review.add_argument("--max-parts", type=int, default=8, help="Maximum small batches to review now (1-64)")
    review.add_argument("--resume", action="store_true", help="Reuse completed batches and continue unattempted work; uncertain requests stay blocked")
    review.add_argument("--retry-uncertain", action="store_true", help="With --resume, explicitly allow another request whose remote outcome is unknown")
    review.add_argument("--offline", action="store_true", help="Produce a coverage plan without an API request")
    review.add_argument("--consent", action="store_true", help="Approve sending admitted folder contents to the configured API")
    review.add_argument("--question", default="Review this material for mistakes, gaps and inconsistencies.")
    research = sub.add_parser("research", help="Build a search-backed evidence report")
    research.add_argument("topic")
    research.add_argument("-o", "--output", default="research_output.md")
    research.add_argument("--no-stream", action="store_true", help="Compatibility flag; reports are validated before display")
    template = sub.add_parser("template", help="Run a built-in or user:NAME template")
    template.add_argument("name")
    template.add_argument("-v", "--var", action="append", default=[], metavar="KEY=VALUE")
    template.add_argument("-o", "--output")
    template.add_argument("--no-stream", action="store_true")
    workbench = sub.add_parser("workbench", help="Run a workflow from a JSON input file")
    workbench.add_argument("file")
    workbench.add_argument("-o", "--output", default="sinter_report.md")
    watches = sub.add_parser("watches", help="List watches or check due queries once")
    watches.add_argument("--run-due", action="store_true")
    speech = sub.add_parser("transcribe", help="Optional local speech recognition; no identity claims")
    speech.add_argument("file")
    speech.add_argument("--consent", action="store_true", help="Confirm permission to process this recording")
    speech.add_argument("--allow-download", action="store_true", help="Allow the separately licensed speech model download")
    speech.add_argument("--model", default="base")
    speech.add_argument("--language", default="auto", help="auto or a language code such as en")
    speech.add_argument("--split-channels", action="store_true", help="Two isolated recording tracks; not voice identification")
    speech.add_argument("--format", choices=["json", "txt", "srt", "vtt"], default="json")
    speech.add_argument("-o", "--output", help="Output file; default transcript.FORMAT")
    sub.add_parser("templates", help="List templates")
    sub.add_parser("health", help="Check the live API")
    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return
    try:
        _dispatch(args)
    except (client.APIError, ValueError, OSError, KeyError) as exc:
        print(f"Sinter: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except KeyboardInterrupt:
        print("\nStopped.", file=sys.stderr)
        raise SystemExit(130)


def _dispatch(args) -> None:
    from .templates import available_templates, resolve_template, template_events
    if args.command == "serve":
        from .server import serve
        serve(args.host, args.port, not args.no_browser)
    elif args.command == "health":
        ok, message = client.health_check()
        print(("OK: " if ok else "FAIL: ") + message)
        raise SystemExit(0 if ok else 1)
    elif args.command == "templates":
        for key, template in available_templates().items():
            print(f"{key}: {template.description}\n  Variables: {', '.join(template.variables)}")
    elif args.command == "chat":
        history = [client.Message("system", args.system)] if args.system else []
        while True:
            try:
                value = args.message if args.message is not None else input("You (quit or clear): ")
            except EOFError:
                return
            if args.message is None and value.strip().lower() in {"quit", "exit", "q"}:
                return
            if args.message is None and value.strip().lower() == "clear":
                history = [message for message in history if message.role == "system"]
                print("Conversation cleared.")
                continue
            if not value.strip():
                if args.message is not None:
                    raise ValueError("Enter a message.")
                continue
            messages = history + [client.Message("user", value)]
            parts = []
            for token in client.chat_stream(messages, args.max_tokens):
                print(token, end="", flush=True)
                parts.append(token)
            print()
            history = messages + [client.Message("assistant", "".join(parts))]
            if args.message is not None:
                return
    elif args.command == "review":
        from .review import atomic_save, load_collection, run
        if args.retry_uncertain and (not args.resume or args.offline):
            raise ValueError("--retry-uncertain requires --resume without --offline.")
        payload, admission = load_collection(args.file)
        if Path(args.file).is_dir() and not (args.consent or args.offline):
            raise ValueError("Folder review sends text to the API. Use --offline to inspect admission, then --consent after checking for private material.")
        output = Path(args.output or (str(Path(args.file)) + ".review.md"))
        receipt = Path(str(output) + ".checkpoint.json")
        saved = None
        if args.resume:
            if receipt.is_symlink() or receipt.stat().st_size > 10_000_000:
                raise ValueError("Invalid or oversized review checkpoint.")
            saved = json.loads(receipt.read_text(encoding="utf-8"))
        result = run(payload, question=args.question, max_parts=args.max_parts, resume=saved,
                     offline=args.offline, language=args.language, retry_uncertain=args.retry_uncertain,
                     on_checkpoint=lambda value: atomic_save(receipt, value),
                     progress=lambda message: print(message, file=sys.stderr))
        result['admission'] = admission
        if not args.offline:
            atomic_save(receipt, result)
        _write(str(output), result['markdown'] + "\n\n## File admission\n\n" + json.dumps(admission, indent=2))
        print(json.dumps(result['coverage'], indent=2))
        if (result['coverage']['batches_failed'] or result['coverage']['batches_uncertain']
                or result['coverage']['batches_partial']):
            raise SystemExit(2)
    elif args.command == "template":
        template, variables, output = resolve_template(args.name), {}, args.output
        for pair in args.var:
            key, sep, value = pair.partition("=")
            if not sep:
                raise ValueError("Template arguments use KEY=VALUE.")
            variables[key] = value
        results, references, streamed = [], [], False
        for event in template_events(template, variables, stream=not args.no_stream):
            if event["type"] == "step":
                streamed = False
                print(f"\n{event['index'] + 1}/{event['total']}: {event['name']}")
            elif event["type"] == "token":
                streamed = True
                print(event["t"], end="", flush=True)
            elif event["type"] == "sources":
                for item in event["sources"]:
                    print("Source: " + item["url"])
                    references.append(item["url"])
            elif event["type"] == "step_done":
                print("" if streamed else event["content"])
                results.append("## " + event["step"] + "\n\n" + event["content"])
                if output:
                    _write(output, "# Model-generated draft - review required\n\n" + "\n\n".join(results))
        if references:
            results.append("## Source register\n\n" + "\n".join(dict.fromkeys(references)))
        if output:
            _write(output, "# Model-generated draft - review required\n\n" + "\n\n".join(results))
    elif args.command in {"research", "workbench"}:
        from .workbench import run
        payload = ({"workflow": "brief", "title": args.topic, "query": args.topic, "use_search": True}
                   if args.command == "research" else json.loads(Path(args.file).read_text(encoding="utf-8")))
        result = run(payload, progress=lambda message: print(message, file=sys.stderr))
        _write(args.output, json.dumps(result, indent=2, ensure_ascii=False) if args.output.endswith(".json") else result["markdown"])
    elif args.command == "watches":
        from .store import Store
        store = Store()
        if args.run_due:
            print(f"Checked {store.run_due()} due watches.")
        print(json.dumps(store.watches(), indent=2, ensure_ascii=False))
    elif args.command == "transcribe":
        from .speech import transcribe
        from .transcript_export import export_transcript
        result = transcribe(Path(args.file), args.model, args.consent, args.allow_download,
                            progress=lambda message: print(message, file=sys.stderr),
                            language=args.language, split_channels=args.split_channels)
        _write(args.output or f"transcript.{args.format}", export_transcript(result, args.format))


def launch() -> None:
    main(sys.argv[1:] or ["serve"])


if __name__ == "__main__":
    main()
