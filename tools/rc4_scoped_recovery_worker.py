"""Current-source reader probes after a stopped fictional scoped-project run."""

from __future__ import annotations

import copy
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools import rc4_recovery_worker as worker  # noqa: E402

TITLE = "Fictional scoped recovery handover"
FRIENDLY = "no choices were cleared"


def cli_reader_environment(home):
    """Use fictional home and Windows Python bootstrap, without caller accounts."""
    from tools.published_rc3_fixture import seed_environment

    return {**seed_environment(home), "HOME": str(home)}


def after_stop(args):
    from sinter.native_window import NativeController
    from sinter.runtime import OperationError, Runtime

    # Observe and retain live metadata BEFORE any Runtime/CLI can initialize it.
    before = worker.snapshot(args.data)
    args.control.with_suffix(".reader-before.json").write_text(
        worker.canonical(before), encoding="utf-8"
    )
    # This is a conservation rehearsal, not a migration qualification. Refuse a
    # changed fixture before a reader can initialize or repair any live value.
    from tools.rc4_scoped_recovery_contract import equal, seed_projection

    seed_path = args.control.parent.parent / "seed-control.json"
    seeded = json.loads(seed_path.read_text(encoding="utf-8"))["seed"]["snapshot"]
    if not equal(seed_projection(before, seeded), seeded):
        raise ValueError("Stopped fixture changed before reader admission")
    # The source repository owns saved projects; Store intentionally owns reports.
    with Runtime(args.data) as current:
        rows = current.call("casebooks.list")["casebooks"]
        row = next((r for r in rows if r["title"] == TITLE), None)
        if row is None:
            raise ValueError("The stopped source has no scoped fixture.")
        saved = current.app.casebooks.get(row["id"])
    books = saved
    backup = args.control.with_suffix(".backup.json")
    backup.write_text(worker.canonical(saved["document"]), encoding="utf-8")
    payload = args.control.with_suffix(".input.json")
    results = {"native": {}, "runtime": {}, "cli": {}}
    native = NativeController(Runtime(args.data))
    local = {
        "schema": "sinter-casebook/v1",
        "title": "Unsaved native input retained 🐝",
        "questions": "Not confirmed?",
        "documents": [],
        "document_type": "brief",
    }
    native.edit_document(local)
    original = copy.deepcopy(native.document)
    downgrade = {
        k: copy.deepcopy(v)
        for k, v in saved["document"].items()
        if k not in {"question_scopes", "scope_fingerprint"}
    }
    downgrade["schema"] = "sinter-casebook/v1"
    operations = {
        "casebooks.get": {"id": saved["id"]},
        "casebooks.validate": {"document": saved["document"]},
        "casebooks.save": {
            "id": saved["id"],
            "revision": saved["revision"],
            "document": downgrade,
        },
        "casebooks.save_scoped": {"document": saved["document"]},
        "casebooks.build": {"id": saved["id"], "revision": saved["revision"]},
        "casebooks.draft": {"id": saved["id"], "revision": saved["revision"]},
    }
    try:
        job_before = native.runtime.app.jobs.list()
        for name, operation in (
            ("open", lambda: native.open_project(saved["id"])),
            ("import", lambda: native.import_project(backup)),
        ):
            try:
                operation()
            except OperationError as error:
                assert FRIENDLY in str(error)
                assert native.document == original and native.dirty is True
                results["native"][name] = str(error)
            else:
                raise ValueError("An unsupported native reader admitted scoped input.")
        # A native v1 resave over a scoped saved ID must refuse without losing edits.
        native.identifier, native.revision = saved["id"], saved["revision"]
        native.edit_document(downgrade)
        for name, operation in (("resave", native.save), ("build", native.start_build)):
            try:
                operation()
            except OperationError as error:
                assert FRIENDLY in str(error)
                assert native.document == downgrade and native.dirty is True
                assert (
                    native.identifier == saved["id"]
                    and native.revision == saved["revision"]
                )
                results["native"][name] = str(error)
            else:
                raise ValueError(
                    "Unsupported native resave admitted scoped stored input."
                )
        native.edit_document(saved["document"])
        text_source = args.control.with_suffix(".native-text.txt")
        text_source.write_text("Fictional additional local note 🐝", encoding="utf-8")
        for name, operation in (
            ("add_text_scoped_local", lambda: native.import_text([text_source])),
            ("resave_scoped_local", native.save),
            ("build_scoped_local", native.start_build),
        ):
            try:
                operation()
            except OperationError as error:
                assert FRIENDLY in str(error)
                assert native.document == saved["document"] and native.dirty is True
                results["native"][name] = str(error)
            else:
                raise ValueError(
                    "Unsupported native local scoped reader admitted input"
                )
        target = args.control.with_suffix(".native-export.json")
        try:
            native.export_project(target)
        except OperationError as error:
            assert FRIENDLY in str(error) and not target.exists()
            assert native.document == saved["document"] and native.dirty is True
            results["native"]["export_scoped_local"] = str(error)
        else:
            raise ValueError("Unsupported native export cleared scope.")
        for name, body in operations.items():
            try:
                native.runtime.call(
                    "casebooks.save" if name == "casebooks.save_scoped" else name, body
                )
            except OperationError as error:
                assert FRIENDLY in str(error)
                results["runtime"][name] = str(error)
            else:
                raise ValueError("Default Python caller admitted scoped input.")
        assert native.runtime.app.jobs.list() == job_before
        results["jobs_unchanged"] = True
    finally:
        native.close()
    # Current CLI explicitly preserves whole JSON and declares v2 capability.
    for name in ("casebooks.get", "casebooks.validate", "casebooks.build", "export"):
        body = operations.get(name, {"id": saved["id"]})
        payload.write_text(worker.canonical(body), encoding="utf-8")
        command = [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-X",
            "utf8",
            str(Path(__file__)),
            "--cli-child",
            str(args.source),
            str(args.data),
            name,
            str(payload),
        ]
        proc = subprocess.run(
            command,
            env=cli_reader_environment(args.data.parent / "home"),
            stdin=subprocess.DEVNULL,
            capture_output=True,
            timeout=20,
            check=False,
        )
        prefix = args.control.with_suffix("." + name.replace(".", "-"))
        prefix.with_suffix(prefix.suffix + ".stdout").write_bytes(proc.stdout)
        prefix.with_suffix(prefix.suffix + ".stderr").write_bytes(proc.stderr)
        envelope = json.loads(proc.stdout)
        assert (
            proc.returncode == 0
            and envelope["ok"] is True
            and envelope["operation"] == ("casebooks.get" if name == "export" else name)
        )
        if name == "casebooks.get":
            assert worker.canonical(envelope["result"]) == worker.canonical(saved)
        if name == "casebooks.validate":
            assert worker.canonical(envelope["result"]["document"]) == worker.canonical(
                saved["document"]
            )
        if name == "casebooks.build":
            assert (
                envelope["result"]["question_scopes"]
                == saved["document"]["question_scopes"]
            )
        if name == "export":
            exported = args.control.with_suffix(".cli-export.json")
            assert worker.canonical(
                json.loads(exported.read_text(encoding="utf-8"))
            ) == worker.canonical(saved["document"])
        results["cli"][name] = {
            "returncode": proc.returncode,
            "ok": envelope["ok"],
            "result": envelope["result"],
        }
    after = worker.snapshot(args.data)
    assert worker.canonical(before) == worker.canonical(after), (
        "Reader probe changed typed local records or settings"
    )
    results.update(snapshot_before=before, snapshot_after=after, stored=books)
    return results


def main():
    if sys.argv[1:2] == ["--cli-child"]:
        source, data, operation, payload = sys.argv[2:]
        sys.path.insert(0, str(Path(source) / "src"))
        from sinter import cli, client

        def refused(*args, **kwargs):
            raise AssertionError("Reader child cannot contact a provider or load keys")

        client._load_key = client._open = client.chat = refused
        import socket

        socket.socket.connect = refused
        if operation == "export":
            identifier = json.loads(Path(payload).read_text(encoding="utf-8"))["id"]
            target = (
                Path(payload)
                .with_suffix(".json")
                .with_name(
                    Path(payload).name.replace(".input.json", ".cli-export.json")
                )
            )
            cli.main(
                [
                    "export",
                    "casebook",
                    identifier,
                    "--directory",
                    data,
                    "-o",
                    str(target),
                    "--machine",
                ]
            )
        else:
            cli.main(
                [
                    "run",
                    operation,
                    "--directory",
                    data,
                    "--input",
                    payload,
                    "--format",
                    "json",
                ]
            )
        return
    # Reuse source bootstrap, paused scheduler and network/opener guards.
    source = Path(sys.argv[sys.argv.index("--source") + 1])
    sys.path.insert(0, str(source / "src"))
    from sinter import client

    def refused(*args, **kwargs):
        raise AssertionError("Scoped recovery cannot read provider keys")

    client._load_key = refused
    worker.main(after_stop=after_stop)


if __name__ == "__main__":
    main()
