"""Discoverable human and machine adapters for the shared in-process runtime."""

from __future__ import annotations

import json
import stat
import sys
from pathlib import Path

from . import __version__
from .outputs import atomic_write_text
from .presentation import result_markdown
from .runtime import (
    RESULT_SCHEMA,
    OperationError,
    Runtime,
    _public_error,
    catalog,
    describe_operation,
    output_sources,
)

COMMANDS = {"operations", "run", "status", "app", "import", "export"}
MAX_INPUT = 36 * 1024 * 1024


def _casebook_capability(operation):
    # This current adapter preserves the whole JSON document. Older adapters
    # using the new runtime do not acquire this capability implicitly.
    return (
        {"casebook_schema": "sinter-casebook/v2"}
        if operation.startswith("casebooks.")
        else {}
    )


def add_parsers(sub):
    operations = sub.add_parser(
        "operations", help="Discover shared UI, CLI and Python operations"
    )
    operations.add_argument(
        "operation", nargs="?", help="Inspect one operation and its input contract"
    )
    operations.add_argument("--format", choices=("text", "json"), default="text")
    run = sub.add_parser(
        "run", help="Run a shared operation directly; no browser or background daemon"
    )
    run.add_argument("operation", help="Stable identifier from sinter operations")
    run.add_argument(
        "--input",
        metavar="FILE|-",
        help="JSON input file, or - for piped JSON; default is {}",
    )
    run.add_argument(
        "--format",
        choices=("text", "json"),
        default="text",
        help="Human output or one structured JSON result on stdout",
    )
    run.add_argument(
        "--directory",
        metavar="PATH",
        help="Existing or new local Sinter workspace; default uses SINTER_DATA_DIR",
    )
    run.add_argument(
        "-o",
        "--output",
        metavar="FILE",
        help="Atomically export the domain result as JSON for later import",
    )
    status = sub.add_parser(
        "status", help="Inspect the local workspace without contacting a provider"
    )
    status.add_argument("--directory", metavar="PATH")
    status.add_argument("--format", choices=("text", "json"), default="text")
    app = sub.add_parser(
        "app", help="Open the same portable runtime as a desktop application"
    )
    app.add_argument(
        "--mode", choices=("native", "browser", "headless"), default="native"
    )
    app.add_argument("--directory", metavar="PATH")

    incoming = sub.add_parser(
        "import", help="Import a casebook or report JSON as a fresh local copy"
    )
    incoming.add_argument("file")
    incoming.add_argument("--kind", choices=("casebook", "report"), required=True)
    incoming.add_argument("--directory", metavar="PATH")
    incoming.add_argument("--format", choices=("text", "json"), default="text")
    outgoing = sub.add_parser(
        "export", help="Export saved sources or a report without changing the original"
    )
    outgoing.add_argument("kind", choices=("casebook", "report"))
    outgoing.add_argument("id", help="Saved identifier from list/import output")
    outgoing.add_argument("-o", "--output", required=True, metavar="FILE")
    outgoing.add_argument("--directory", metavar="PATH")
    outgoing.add_argument(
        "--format",
        choices=("json", "markdown"),
        default="json",
        help="File format; casebook Markdown builds the existing source-only report",
    )
    outgoing.add_argument(
        "--machine",
        action="store_true",
        help="Print one structured result instead of a human confirmation",
    )


def _read_input(name):
    if name is None:
        return {}, ()
    if name == "-":
        if sys.stdin.isatty():
            raise ValueError(
                (
                    "Pipe a JSON object to --input -, or choose --input FILE. "
                    "No interactive input is requested."
                )
            )
        raw = sys.stdin.read(MAX_INPUT + 1)
        sources = ()
    else:
        source = Path(name).expanduser()
        if not stat.S_ISREG(source.stat().st_mode):
            raise ValueError("Choose a regular JSON input file.")
        if source.stat().st_size > MAX_INPUT:
            raise ValueError("The input exceeds the 36 MB request limit.")
        raw = source.read_text(encoding="utf-8")
        sources = (source,)
    if len(raw.encode("utf-8")) > MAX_INPUT:
        raise ValueError("The input exceeds the 36 MB request limit.")

    def invalid_constant(value):
        raise ValueError("JSON must not contain NaN or Infinity.")

    payload = json.loads(raw, parse_constant=invalid_constant)
    if not isinstance(payload, dict):
        raise ValueError("The input must be a JSON object.")
    return payload, sources


def _export_sources(directory, destination, sources=()):
    return output_sources(directory, destination, sources)


def _import_payload(kind, value):
    if kind == "casebook":
        # Native and CLI exports contain the normalized document. Also accept
        # the existing API's saved envelope without transplanting workspace IDs.
        document = (
            value.get("document") if isinstance(value.get("document"), dict) else value
        )
        return {"document": document}
    report = value.get("report") if isinstance(value.get("report"), dict) else value
    return {"report": report}


def _human(value):
    if isinstance(value, dict) and "operations" in value:
        return (
            "Sinter shared operations\n\n"
            + "\n".join(
                f"{row['id']:<24} {row['summary']}" for row in value["operations"]
            )
            + "\n\nInspect: sinter operations OPERATION\n"
            "Run: sinter run OPERATION --input request.json --format json\n"
            "Python: with Runtime(directory) as app: app.call(OPERATION, payload)\n"
            "Provider operations use the saved connection. Preview exact source "
            "requests before approving transfer.\n"
            "Account setup and settings changes remain in the UI."
        )
    if isinstance(value, dict) and all(
        key in value for key in ("id", "summary", "input")
    ):
        return (
            f"{value['id']}\n{value['summary']}\n\n"
            f"Input: {value['input']}\nEffect: {value['effect']}"
        )
    if isinstance(value, dict) and value.get("schema") == "sinter-runtime-status/v1":
        connection = value["connection"]
        lines = [
            f"Sinter {value['version']}",
            f"Workspace: {value['workspace']}",
            f"Configured model: {connection['model']} ({connection['provider']})",
            f"Destination: {connection['api_url']}",
            "Provider generation has not been tested by this status check.",
            ", ".join(f"{amount} {name}" for name, amount in value["counts"].items()),
        ]
        if value.get("preferences_warning"):
            lines.append(value["preferences_warning"])
        if value.get("model_selection_help"):
            lines.append(value["model_selection_help"])
        if value.get("connection_warning"):
            lines.append(value["connection_warning"])
        return "\n".join(lines)
    if isinstance(value, dict) and isinstance(value.get("markdown"), str):
        return value["markdown"]
    if isinstance(value, dict) and isinstance(value.get("results"), list):
        return result_markdown(value)
    return json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)


def _envelope(operation, *, result=None, error=None):
    value = {
        "schema": RESULT_SCHEMA,
        "version": __version__,
        "operation": operation,
        "ok": error is None,
    }
    if error is None:
        value["result"] = result
    else:
        value["error"] = error.public()
    return value


def dispatch(args):
    if args.command == "app":
        from .desktop import main

        arguments = ["--mode", args.mode]
        if args.directory:
            arguments.extend(["--directory", args.directory])
        raise SystemExit(main(arguments))
    operation = getattr(args, "operation", None) or (
        "runtime.status" if args.command == "status" else "operations"
    )
    machine = args.machine if args.command == "export" else args.format == "json"
    if args.command == "import":
        operation = "casebooks.save" if args.kind == "casebook" else "reports.save"
    elif args.command == "export":
        operation = "casebooks.get" if args.kind == "casebook" else "reports.get"
    try:
        if args.command == "operations":
            result = catalog()
            if args.operation:
                result = describe_operation(args.operation)
        elif args.command == "import":
            value, _ = _read_input(args.file)
            with Runtime(args.directory) as runtime:
                result = runtime.call(
                    operation,
                    _import_payload(args.kind, value),
                    **_casebook_capability(operation),
                )
        elif args.command == "export":
            sources = _export_sources(args.directory, args.output)
            with Runtime(args.directory) as runtime:
                saved = runtime.call(
                    operation, {"id": args.id}, **_casebook_capability(operation)
                )
                value = saved["document"] if args.kind == "casebook" else saved
                if args.format == "markdown":
                    if args.kind == "casebook":
                        value = runtime.call(
                            "casebooks.build",
                            {"id": saved["id"], "revision": saved["revision"]},
                            progress=lambda message: print(message, file=sys.stderr),
                            casebook_schema="sinter-casebook/v2",
                        )
                    content = value["markdown"]
                else:
                    content = (
                        json.dumps(value, ensure_ascii=False, indent=2, allow_nan=False)
                        + "\n"
                    )
            atomic_write_text(args.output, content, sources=sources)
            result = {
                "exported": str(args.output),
                "kind": args.kind,
                "format": args.format,
            }
            print(f"Saved: {args.output}", file=sys.stderr)
        else:
            payload, sources = _read_input(getattr(args, "input", None))
            output = getattr(args, "output", None)
            if output:
                sources = _export_sources(args.directory, output, sources)
            # Discovery and admission occur before touching a workspace.
            describe_operation(operation)
            with Runtime(args.directory) as runtime:
                result = runtime.call(
                    operation,
                    payload,
                    progress=lambda message: print(message, file=sys.stderr),
                    **_casebook_capability(operation),
                )
            if output:
                atomic_write_text(
                    output,
                    json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False)
                    + "\n",
                    sources=sources,
                )
                print(f"Saved: {output}", file=sys.stderr)
        if machine:
            # ASCII escapes preserve Unicode JSON values on redirected legacy
            # consoles as well as UTF-8 clients; readable text mode is unchanged.
            print(
                json.dumps(
                    _envelope(operation, result=result),
                    ensure_ascii=True,
                    allow_nan=False,
                )
            )
        else:
            print(_human(result))
    except KeyboardInterrupt:
        error = OperationError(
            (
                "Stopped; no request was replayed. Inspect any saved partial "
                "result before retrying."
            ),
            code="interrupted",
            status=409,
        )
        if machine:
            print(
                json.dumps(
                    _envelope(operation, error=error),
                    ensure_ascii=True,
                    allow_nan=False,
                )
            )
        print(str(error), file=sys.stderr)
        raise SystemExit(130) from None
    except Exception as exc:
        error = _public_error(exc)
        if machine:
            print(
                json.dumps(
                    _envelope(operation, error=error),
                    ensure_ascii=True,
                    allow_nan=False,
                )
            )
        print(f"Sinter: {error}", file=sys.stderr)
        if error.code in {
            "invalid_input",
            "unknown_operation",
            "unsupported_operation",
        }:
            code = 2
        elif error.code == "cancelled":
            code = 130
        else:
            code = 1
        raise SystemExit(code) from None
