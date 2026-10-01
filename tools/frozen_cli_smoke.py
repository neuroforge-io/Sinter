"""Exercise the packaged command dispatcher using only fictional offline work."""

from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
import tempfile
import time
from pathlib import Path


class Commands:
    """Run serial, bounded commands with an isolated home and workspace."""

    def __init__(self, prefix, directory, receipt):
        self.prefix = [str(value) for value in prefix]
        self.directory = Path(directory)
        self.receipt = receipt
        self.deadline = time.monotonic() + 90
        self.environment = {
            key: os.environ[key]
            for key in ("PATH", "SystemRoot", "WINDIR", "COMSPEC", "PATHEXT")
            if key in os.environ
        }
        home = self.directory / "home"
        home.mkdir()
        self.environment.update(
            HOME=str(home), USERPROFILE=str(home), TMP=str(home), TEMP=str(home),
            XDG_CONFIG_HOME=str(home), SINTER_DATA_DIR=str(self.directory / "work"),
        )

    def run(self, name, arguments, *, code=0):
        start = time.monotonic()
        remaining = self.deadline - start
        if remaining <= 0:
            raise RuntimeError("Packaged CLI workflow exceeded its 90-second budget.")
        row = {"check": name, "passed": False}
        self.receipt["checks"].append(row)
        with tempfile.TemporaryFile() as stdout, tempfile.TemporaryFile() as stderr:
            process = subprocess.Popen(
                [*self.prefix, *arguments], env=self.environment,
                cwd=self.directory, stdin=subprocess.DEVNULL,
                stdout=stdout, stderr=stderr, start_new_session=os.name == "posix",
            )
            row["pid"] = process.pid
            try:
                deadline = start + min(20, remaining)
                while process.poll() is None:
                    if any(os.fstat(stream.fileno()).st_size > 1024 * 1024
                           for stream in (stdout, stderr)):
                        raise RuntimeError(
                            f"Packaged CLI {name} exceeded output bound."
                        )
                    if time.monotonic() >= deadline:
                        raise RuntimeError(f"Packaged CLI {name} exceeded time bound.")
                    time.sleep(0.02)
            finally:
                if process.poll() is None:
                    row["forced_cleanup"] = True
                    if os.name == "posix":
                        try:
                            os.killpg(process.pid, signal.SIGTERM)
                        except ProcessLookupError:
                            pass
                    else:
                        process.terminate()
                    try:
                        process.wait(timeout=2)
                    except subprocess.TimeoutExpired:
                        if os.name == "posix":
                            try:
                                os.killpg(process.pid, signal.SIGKILL)
                            except ProcessLookupError:
                                pass
                        else:
                            process.kill()
                        process.wait(timeout=2)
                row["owned_process_exited"] = process.poll() is not None
                row.update(
                    seconds=round(time.monotonic() - start, 4),
                    exit_code=process.returncode,
                )
            stdout.seek(0)
            stderr.seek(0)
            output = stdout.read(1024 * 1024 + 1)
            errors = stderr.read(1024 * 1024 + 1)
            if max(len(output), len(errors)) > 1024 * 1024:
                raise RuntimeError(f"Packaged CLI {name} exceeded output bound.")
            result = subprocess.CompletedProcess(
                process.args, process.returncode,
                output.decode("utf-8"), errors.decode("utf-8"),
            )
        if result.returncode != code or "Traceback" in result.stderr:
            row.update(stdout=result.stdout[:65536], stderr=result.stderr[:65536])
            raise RuntimeError(
                f"Packaged CLI {name} failed (exit {result.returncode})."
            )
        row["passed"] = True
        return result

    def json(self, name, arguments, *, code=0):
        result = self.run(name, arguments, code=code)
        value = json.loads(result.stdout)
        assert value["schema"] == "sinter-operation-result/v1", name
        assert value["ok"] is (code == 0), name
        return value["result"] if code == 0 else value["error"]

    def operation(self, name, operation, payload=None, *, code=0):
        arguments = ["run", operation, "--format", "json"]
        if payload is not None:
            request = self.directory / "request.json"
            request.write_text(json.dumps(payload), encoding="utf-8")
            arguments.extend(["--input", str(request)])
        return self.json(name, arguments, code=code)


def workflow(commands):
    """Use the same import, operations, persistence and export as a human caller."""
    help_text = commands.run("discoverable_help", ["--help"]).stdout
    assert all(word in help_text for word in ("operations", "status", "run", "import"))
    catalogue = commands.json("operation_catalogue", ["operations", "--format", "json"])
    assert {"casebooks.save", "casebooks.build", "reports.get"} <= {
        row["id"] for row in catalogue["operations"]
    }
    document = {
        "title": "Fictional Lantern library \u03a9",
        "questions": "How long is the lending period?\nZebra insurance premium?",
        "documents": [{
            "title": "Fictional handbook.md",
            "content": "The Lantern lending period is 14 days. Fictional label \u03a9.",
        }],
    }
    source = commands.directory / "fictional-\u03a9.json"
    source.write_text(json.dumps(document), encoding="utf-8")
    saved = commands.json("import_material", [
        "import", str(source), "--kind", "casebook", "--format", "json"
    ])
    assert commands.operation("inspect_sources", "casebooks.get", {
        "id": saved["id"]
    }) == saved
    report = commands.operation("inspect_evidence_and_gap", "casebooks.build", {
        "id": saved["id"], "revision": saved["revision"]
    })
    assert "14 days" in report["markdown"] and report["excerpts"]
    assert report["question_index"][1]["excerpt_ids"] == []
    assert report["sources"][0]["content"] == document["documents"][0]["content"]
    historical = commands.operation("retain_report", "reports.save", {"report": report})
    document["documents"][0]["content"] = (
        "The Lantern lending period is 21 days. Fictional label \u03a9."
    )
    updated = commands.operation("update_sources", "casebooks.save", {
        "id": saved["id"], "revision": saved["revision"], "document": document
    })
    assert updated["id"] == saved["id"] and updated["revision"] == 2
    latest = commands.operation("inspect_updated_evidence", "casebooks.build", {
        "id": updated["id"], "revision": updated["revision"]
    })
    assert "21 days" in latest["markdown"] and latest["excerpts"]
    assert commands.operation("historical_snapshot", "reports.get", {
        "id": historical["id"]
    }) == report
    commands.operation("refuse_stale_update", "casebooks.save", {
        "id": saved["id"], "revision": saved["revision"], "document": document
    }, code=2)
    assert commands.operation("stale_update_keeps_sources", "casebooks.get", {
        "id": saved["id"]
    }) == updated
    exported = commands.directory / "exported-\u03a9.json"
    commands.json("export_sources", [
        "export", "casebook", saved["id"], "-o", str(exported), "--machine"
    ])
    assert json.loads(exported.read_text(encoding="utf-8")) == updated["document"], (
        "UTF-8 exported backup changed."
    )
    restored = commands.json("restore_separate_workspace", [
        "import", str(exported), "--kind", "casebook", "--format", "json",
        "--directory", str(commands.directory / "restored"),
    ])
    assert restored["id"] != saved["id"] and restored["document"] == updated["document"]
    status = commands.json("reopened_status", ["status", "--format", "json"])
    assert status["counts"]["casebooks"] == 1 and status["counts"]["reports"] == 1
    error = commands.operation(
        "unknown_operation_json_error", "fictional.not_supported", code=2
    )
    assert error["code"] == "unknown_operation"
    return len(catalogue["operations"])


def qualify(binary):
    """Return actual frozen-process evidence; never a real-model qualification."""
    binary = Path(binary).resolve()
    receipt = {
        "schema": "sinter-frozen-cli-test/v1", "passed": False, "checks": [],
        "fixture_only": True, "provider_inference_exercised": False,
        "credentials_supplied": False, "gui_exercised": False,
    }
    start = time.monotonic()
    try:
        digest = hashlib.sha256()
        with binary.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
        receipt["binary_sha256"] = digest.hexdigest()
        with tempfile.TemporaryDirectory(prefix="sinter-frozen-cli-") as directory:
            commands = Commands([binary], directory, receipt)
            diagnostics = json.loads(
                commands.run("frozen_identity", ["--diagnose"]).stdout
            )
            assert (
                diagnostics["frozen"] is True and diagnostics["core_assets_available"]
            )
            receipt["version"] = diagnostics["version"]
            receipt["operations_discovered"] = workflow(commands)
        receipt.update(passed=True, temporary_workspace_removed=True)
    except Exception as exc:
        stage = receipt["checks"][-1] if receipt["checks"] else {}
        stage["passed"] = False
        receipt.update(
            error_type=type(exc).__name__,
            error=str(exc) or f"{stage.get('check', 'preflight')} contract failed.",
        )
    receipt["seconds"] = round(time.monotonic() - start, 4)
    return receipt
