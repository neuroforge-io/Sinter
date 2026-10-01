"""Qualify a copied fictional workspace through an installed candidate's API.

No real workspace or credentials are read. Run the native process in an offline
container; this check establishes upgrade preservation, not live model access.
"""

from __future__ import annotations

import argparse
import hashlib
import http.cookiejar
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.installed_workflow_browser import browser_launch_command  # noqa: E402
from tools.qualified_priors import (  # noqa: E402
    PRIOR_COMMIT,
    QUALIFIED_PRIORS,
    PriorRelease,
    qualified_prior,
)

MAX_PRIOR_ARCHIVE_BYTES = 64 * 1024 * 1024
MAX_PRIOR_SOURCE_BYTES = 256 * 1024 * 1024
MAX_PRIOR_SOURCE_ENTRIES = 10_000


def file_sha256(path: Path) -> str:
    """Hash qualification inputs without loading arbitrary selected files into RAM."""
    result = hashlib.sha256()
    with path.open("rb") as source:
        while chunk := source.read(1024 * 1024):
            result.update(chunk)
    return result.hexdigest()


def admitted_source_files(
    source: Path,
    sizes: dict[str, int],
    directories: set[str],
) -> dict[str, Path]:
    """Reject foreign or oversized extracted entries before any content hashing."""
    observed = {}
    total = 0
    entries = 0
    for path in source.rglob("*"):
        entries += 1
        if entries > MAX_PRIOR_SOURCE_ENTRIES:
            raise ValueError("Extracted prior source exceeds the entry bound.")
        name = path.relative_to(source).as_posix()
        info = path.lstat()
        if stat.S_ISDIR(info.st_mode):
            if name not in directories:
                raise ValueError("Extracted prior source has an unexpected directory.")
            continue
        if not stat.S_ISREG(info.st_mode):
            raise ValueError(
                "Extracted prior source requires regular files, not links."
            )
        if name not in sizes:
            raise ValueError("Extracted prior source has an unexpected file.")
        if info.st_size != sizes[name]:
            raise ValueError(
                "Extracted prior source file size differs from its archive."
            )
        total += info.st_size
        if total > MAX_PRIOR_SOURCE_BYTES:
            raise ValueError("Extracted prior source exceeds the total size bound.")
        observed[name] = path
    if set(observed) != set(sizes):
        raise ValueError("Extracted prior source differs from its published archive.")
    return observed


def verify_prior_source(
    source: Path,
    archive: Path,
    prior: PriorRelease,
) -> dict[str, str]:
    """Bind all imported fixture code to the exact published source ZIP bytes."""
    if qualified_prior(prior.version, prior.source_commit) != prior:
        raise ValueError("Prior source hashes differ from the qualified release pin.")
    if not archive.is_file() or archive.is_symlink():
        raise ValueError("Provide the actual published prior source archive.")
    if archive.stat().st_size > MAX_PRIOR_ARCHIVE_BYTES:
        raise ValueError("Prior source archive exceeds the qualification size bound.")
    if file_sha256(archive) != prior.source_archive_sha256:
        raise ValueError("Prior source archive differs from its qualified checksum.")
    if not source.is_dir() or source.is_symlink():
        raise ValueError("Provide the extracted published prior source.")
    expected = {}
    sizes = {}
    directories = set()
    with zipfile.ZipFile(archive) as bundle:
        for row in bundle.infolist():
            name = row.filename.rstrip("/") if row.is_dir() else row.filename
            path = PurePosixPath(name)
            if (
                not name
                or path.is_absolute()
                or ".." in path.parts
                or path.as_posix() != name
                or "\\" in name
                or ":" in name
                or "\x00" in name
                or (row.external_attr >> 16) & 0o170000 not in {0, 0o040000, 0o100000}
            ):
                raise ValueError("The prior source archive has an unsafe entry.")
            if row.is_dir():
                directories.add(name)
                continue
            if name in sizes or row.file_size > MAX_PRIOR_ARCHIVE_BYTES:
                raise ValueError("The prior source archive has an invalid file.")
            sizes[name] = row.file_size
            directories.update(
                parent.as_posix()
                for parent in path.parents
                if parent != PurePosixPath(".")
            )
        if (
            not sizes
            or len(sizes) + len(directories) > MAX_PRIOR_SOURCE_ENTRIES
            or sum(sizes.values()) > MAX_PRIOR_SOURCE_BYTES
        ):
            raise ValueError("The prior source archive exceeds its content bounds.")
        files = admitted_source_files(source, sizes, directories)
        for name, path in files.items():
            expected[name] = hashlib.sha256(bundle.read(name)).hexdigest()
            if file_sha256(path) != expected[name]:
                raise ValueError(
                    "Extracted prior source differs from its published archive."
                )
    return expected


def prior_for_arguments(args) -> PriorRelease:
    """Validate prior and candidate selection before creating any workspace."""
    prior = qualified_prior(args.prior_version, args.prior_commit)
    targets = {
        "0.5.3": {"0.5.4rc1", "0.5.4rc2", "0.5.4rc3"},
        "0.5.4rc1": {"0.5.4rc2", "0.5.4rc3"},
        "0.5.4rc2": {"0.5.4rc3"},
    }
    if args.expected_version not in targets[prior.version]:
        raise ValueError(
            "The prior and candidate have no explicitly qualified upgrade path."
        )
    return prior


SEED = r"""
import json, socket, sys
from pathlib import Path
prior, directory, output = map(Path, sys.argv[1:4])
expected_version = sys.argv[4]
sys.path.insert(0, str(prior / "src"))
socket.socket.connect = lambda *args: (_ for _ in ()).throw(
    AssertionError("Fixture seeding must not use the network"))
from sinter import __version__, casebooks
from sinter.campaigns import CampaignStore
from sinter.preferences import Preferences
from sinter.store import Store
assert __version__ == expected_version, "Fixture must use the actual prior release"
directory.mkdir()
store = Store(directory)
preferences = Preferences(directory)
preferences.update({
    "theme":"light", "text_size":"large", "density":"compact",
    "reduce_motion":True, "model":"erais-fracture-gemma", "max_tokens":512,
    "full_name":"Morgan Example", "organisation":"Fictional Garden Group",
    "email":"morgan@example.invalid", "location":"Fictional Riverbank",
})
source = ("Fictional note — the garden venue is not confirmed. "
          "Water approval is unknown.")
book = casebooks.Casebooks(store).save({
    "title":"Fictional upgrade casebook", "questions":"Is the garden venue confirmed?",
    "documents":[{"title":"Fictional venue note", "content":source,
                  "url":"https://example.invalid/venue", "date":"2026-09-12"}],
})
campaign_document = {
    "title":"Fictional upgrade funding campaign",
    "organisation":"Fictional Garden Group",
    "objective":"Confirm venue permission before applying.",
    "opportunities":[{"name":"Fictional Garden Fund", "status":"clarification"}],
    "requirements":[{"opportunity":"Fictional Garden Fund", "rule":"Venue permission",
                     "status":"unknown", "evidence":"Permission not received."}],
    "actions":[{"task":"Request venue permission", "owner":"Morgan Example",
                "status":"open"}],
}
if expected_version in {"0.5.4rc1", "0.5.4rc2"}:
    campaign_document["sources"] = [{
        "id":"a" * 32, "title":"Fictional changed programme page",
        "url":"https://example.invalid/current-round", "checked_at":"2026-09-29",
        "notes":"Current source differs from the retained earlier check.",
    }]
    campaign_document["requirements"][0].update({
        "source_id":"a" * 32, "source_url":"https://example.invalid/earlier-round",
        "source_quote":"Venue permission must be obtained before applying.",
        "checked_at":"2026-09-12",
    })
    campaign_document["actions"][0].update({
        "owner_kind":"unknown", "owner_confirmed":False, "due":"2026-10-09",
    })
    campaign_document["actions"].append({
        "task":"Check water approval", "owner":"", "owner_kind":"unassigned",
        "owner_confirmed":False, "status":"open", "due":"",
    })
    if expected_version == "0.5.4rc2":
        # A retained user mark is deliberately unsupported by the changed source.
        campaign_document["requirements"][0]["status"] = "met"
campaign = CampaignStore(directory).save(campaign_document)
report = {
    "title":"Fictional retained draft", "workflow":"brief",
    "markdown":"# Original source-only draft\n\n" + source,
    "document_markdown":"# Garden venue enquiry\n\nPlease confirm venue permission.",
    "sources":[{"id":"Sfictional", "title":"Fictional venue note",
                "url":"https://example.invalid/venue"}],
    "excerpts":[{"id":"Efictional", "source_id":"Sfictional", "quote":source}],
    "document_edits":{"markdown":("# Reviewed garden enquiry\n\n"
                                  "Venue approval is still needed."),
                      "edited_at":"2026-09-12T12:00:00Z", "author":"user"},
}
report_id = store.save_report(report)
watch_id = store.add_watch("Fictional disabled watch", "fictional garden grant", 86400)
store.change_watch(watch_id, False)
expected = {
    "prior_version":__version__, "settings":preferences.snapshot(),
    "campaign":campaign, "casebook":book, "report_id":report_id, "report":report,
    "watch":next(row for row in store.watches() if row["id"] == watch_id),
    "source_text":source,
}
output.write_text(json.dumps(expected, ensure_ascii=False, indent=2), encoding="utf-8")
"""


def hashes(directory: Path) -> dict[str, str]:
    """Record fixture bytes without following a link to an unrelated workspace."""
    result = {}
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Upgrade fixtures must not contain symbolic links.")
        if path.is_file():
            result[path.relative_to(directory).as_posix()] = file_sha256(path)
    return result


def assert_preserved(prior, current, label: str):
    """Allow additive schema defaults while preserving every existing value."""
    if isinstance(prior, dict):
        assert isinstance(current, dict), f"Changed object: {label}"
        for key, value in prior.items():
            assert key in current, f"Removed field: {label}.{key}"
            assert_preserved(value, current[key], f"{label}.{key}")
    elif isinstance(prior, list):
        assert isinstance(current, list) and len(prior) == len(current), (
            f"Changed rows: {label}"
        )
        for index, value in enumerate(prior):
            assert_preserved(value, current[index], f"{label}[{index}]")
    else:
        assert type(prior) is type(current) and prior == current, (
            f"Changed original value: {label}"
        )


def loopback_base(value: str) -> str:
    parsed = urlsplit(value.strip())
    if (
        parsed.scheme != "http"
        or parsed.hostname != "127.0.0.1"
        or not parsed.port
        or parsed.username
        or parsed.password
        or parsed.path not in {"", "/"}
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("The candidate must open its own loopback HTTP address.")
    return f"http://127.0.0.1:{parsed.port}"


class LocalAPI:
    def __init__(self, base: str):
        self.base, self.token = loopback_base(base), ""
        self.opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({}),
            urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        )

    def request(self, path: str, data: dict | None = None):
        if not path.startswith("/api/") or ".." in path:
            raise ValueError("Upgrade inspection uses only local API routes.")
        request = urllib.request.Request(
            self.base + path,
            data=json.dumps(data).encode() if data is not None else None,
            headers={"Content-Type": "application/json", "X-Sinter-Token": self.token},
        )
        with self.opener.open(request, timeout=10) as response:
            raw = response.read(2_000_001)
        if len(raw) > 2_000_000:
            raise ValueError("The local qualification response is too large.")
        return json.loads(raw)


def check_preserved(api: LocalAPI, expected: dict, *, legacy=False) -> list[str]:
    settings = api.request("/api/settings")
    if settings.get("warning"):
        raise AssertionError("Prior preferences fell back to defaults.")
    for key, value in expected["settings"].items():
        assert settings["settings"][key] == value, f"Changed preference: {key}"
    if not legacy:
        assert settings["settings"]["provider"] == "openai-compatible"
    assert not settings["has_session_key"]
    campaign = expected["campaign"]
    campaign_current = api.request("/api/campaigns/" + campaign["id"])
    assert_preserved(campaign, campaign_current, "campaign")
    for opportunity in campaign_current["document"]["opportunities"]:
        assert opportunity.get("application_window", "unknown") == "unknown"
        assert opportunity.get("applicant_confirmed", False) is False
    for action in campaign_current["document"]["actions"]:
        assert action.get("owner_confirmed", False) is False
    book = expected["casebook"]
    book_current = api.request("/api/casebooks/" + book["id"])
    assert_preserved(book, book_current, "casebook")
    assert_preserved(
        expected["report"],
        api.request("/api/reports/" + expected["report_id"]),
        "report",
    )
    watches = api.request("/api/watches")["watches"]
    assert_preserved([expected["watch"]], watches, "watches")
    assert not watches[0]["enabled"]
    job = api.request(
        "/api/casebooks/build", {"id": book["id"], "revision": book["revision"]}
    )
    identifier = job.get("id") or job.get("job_id")
    assert identifier, "Source-only casebook job was not created."
    deadline = time.monotonic() + 20
    while time.monotonic() < deadline:
        result = api.request("/api/jobs/" + identifier)
        if result["status"] == "done":
            assert result["result"]["coverage"]["documents_supplied"] == 1
            assert expected["source_text"] in result["result"]["markdown"]
            break
        if result["status"] in {"failed", "cancelled"}:
            raise AssertionError("The retained source-only casebook could not run.")
        time.sleep(0.05)
    else:
        raise AssertionError("Source-only casebook job did not complete in time.")
    assert api.request("/api/campaigns/" + campaign["id"]) == campaign_current
    assert api.request("/api/casebooks/" + book["id"]) == book_current
    checks = [
        "prior profile and appearance preferences retained",
        "explicit legacy model selection retained"
        + (" by prior application" if legacy else " with compatible provider"),
        "campaign and casebook identities, revisions and original data retained",
        "saved report, source evidence and user edits retained",
        "disabled watch retained without a search request",
        "retained source-only casebook completed through installed API",
    ]
    if expected.get("prior_version") == "0.5.4rc2":
        document = campaign_current["document"]
        assert len(document["sources"]) == 1 and len(document["actions"]) == 2
        requirement, source = document["requirements"][0], document["sources"][0]
        assert requirement["status"] == "met"
        assert requirement["source_id"] == source["id"] == "a" * 32
        assert requirement["source_url"] == "https://example.invalid/earlier-round"
        assert source["url"] == "https://example.invalid/current-round"
        assert requirement["checked_at"] == "2026-09-12"
        assert source["checked_at"] == "2026-09-29"
        assert [row["owner_kind"] for row in document["actions"]] == [
            "unknown",
            "unassigned",
        ]
        prepared = api.request("/api/campaigns/prepare", {"document": document})
        assert prepared["readiness"]["claims_without_evidence"] == 1
        assert prepared["readiness"]["requirements_unresolved"] == 1
        assert api.request("/api/campaigns/" + campaign["id"]) == campaign_current
        assert_preserved(
            expected["report"],
            api.request("/api/reports/" + expected["report_id"]),
            "historical report",
        )
        checks.append(
            "rich prior source snapshots, stale marked review "
            "and unknown/unassigned owners retained"
        )
    return checks


def prepare_fixture(
    prior_source: Path,
    output: Path,
    *,
    prior: PriorRelease,
    prior_source_archive: Path,
):
    source_hashes = verify_prior_source(prior_source, prior_source_archive, prior)
    output = output.resolve()
    source = prior_source.resolve()
    if output.is_relative_to(source) or source.is_relative_to(output):
        raise ValueError("Keep the fixture output separate from prior source inputs.")
    if output.exists() and any(output.iterdir()):
        raise ValueError(
            "Choose a fresh output folder; existing fixtures are preserved."
        )
    output.mkdir(parents=True, exist_ok=True)
    original, copied = output / "prior-workspace", output / "candidate-workspace"
    if original.exists() or copied.exists():
        raise ValueError(
            "Choose a fresh output folder; existing fixtures are preserved."
        )
    expected_path = output / "prior-fixture.json"
    subprocess.run(
        [
            sys.executable,
            "-I",
            "-S",
            "-B",
            "-c",
            SEED,
            str(prior_source.resolve()),
            str(original),
            str(expected_path),
            prior.version,
        ],
        env={
            key: value
            for key, value in os.environ.items()
            if key
            not in {
                "NEUROFORGE_BASE_URL",
                "NEUROFORGE_MODEL",
                "NEUROFORGE_API_KEY",
                "OPENAI_API_KEY",
                "ANTHROPIC_API_KEY",
            }
        },
        check=True,
        timeout=30,
    )
    expected = json.loads(expected_path.read_text(encoding="utf-8"))
    assert expected["prior_version"] == prior.version
    assert (
        verify_prior_source(prior_source, prior_source_archive, prior) == source_hashes
    ), "Prior source bytes were changed."
    original_hashes = hashes(original)
    shutil.copytree(original, copied)
    return expected, original, copied, original_hashes


def run_native(
    binary: Path,
    directory: Path,
    expected: dict,
    output: Path,
    version: str,
    *,
    legacy=False,
):
    label = "prior" if legacy else "candidate"
    preferences_hash = hashes(directory)["preferences.json"]
    capture = output / f"capture-{label}-browser-url.py"
    capture.write_text(
        "import sys\nfrom pathlib import Path\n"
        "Path(sys.argv[1]).write_text(sys.argv[2], encoding='utf-8')\n",
        encoding="utf-8",
    )
    captured = output / f"{label}-loopback-url.txt"
    environment = dict(os.environ)
    for name in (
        "NEUROFORGE_BASE_URL",
        "NEUROFORGE_MODEL",
        "NEUROFORGE_API_KEY",
        "OPENAI_API_KEY",
        "ANTHROPIC_API_KEY",
    ):
        environment.pop(name, None)
    environment["SINTER_DATA_DIR"] = str(directory)
    environment["BROWSER"] = shlex.join(
        [sys.executable, str(capture), str(captured), "%s"]
    )
    binary = binary.resolve()
    actual = subprocess.run(
        [str(binary), "--version"],
        capture_output=True,
        text=True,
        check=True,
        timeout=10,
    ).stdout.strip()
    assert actual == version, "Candidate binary version did not match."
    api = None
    with (output / f"{label}-process.log").open("w", encoding="utf-8") as log:
        process = subprocess.Popen(
            # Legacy selects preservation checks, not the binary's presentation.
            browser_launch_command([str(binary)], actual),
            env=environment,
            stdout=log,
            stderr=log,
        )
        try:
            deadline = time.monotonic() + 20
            while not captured.exists() and time.monotonic() < deadline:
                if process.poll() is not None:
                    raise AssertionError(
                        "Installed candidate stopped before opening its UI."
                    )
                time.sleep(0.05)
            if not captured.exists():
                raise AssertionError(
                    "Installed candidate did not open its local UI in time."
                )
            api = LocalAPI(captured.read_text(encoding="utf-8"))
            session = api.request("/api/session")
            assert session["version"] == version and session["desktop"] is True
            api.token = session["token"]
            checks = check_preserved(api, expected, legacy=legacy)
            assert hashes(directory)["preferences.json"] == preferences_hash
            checks.append(
                "opening candidate did not rewrite the prior preferences file"
            )
        finally:
            if api is not None and process.poll() is None:
                try:
                    api.request("/api/desktop/quit", {})
                    process.wait(timeout=5)
                except (OSError, ValueError, subprocess.TimeoutExpired):
                    pass
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait(timeout=5)
    return actual, checks


def qualify(args) -> dict:
    prior = prior_for_arguments(args)
    output = args.output.resolve()
    expected, original, copied, original_hashes = prepare_fixture(
        args.prior_source,
        output,
        prior=prior,
        prior_source_archive=args.prior_source_archive,
    )
    binary = args.candidate_binary.resolve()
    actual, checks = run_native(binary, copied, expected, output, args.expected_version)
    assert hashes(original) == original_hashes
    checks.append("untouched prior workspace retains every original file digest")
    return {
        "schema": "sinter-copied-upgrade-test/v1",
        "passed": True,
        "fixture_notice": (
            "Fictional workspace only. No live model access or real account proof."
        ),
        "prior_version": expected["prior_version"],
        "prior_source_commit": prior.source_commit,
        "prior_source_archive_sha256": prior.source_archive_sha256,
        "candidate_version": actual,
        "candidate_source_commit": args.source_commit,
        "candidate_binary_sha256": file_sha256(binary),
        "original_fixture_hashes": original_hashes,
        "checks": checks,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prior-source", type=Path, required=True)
    parser.add_argument("--prior-source-archive", type=Path, required=True)
    parser.add_argument("--candidate-binary", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--source-commit", required=True)
    parser.add_argument(
        "--prior-version", choices=list(QUALIFIED_PRIORS), default="0.5.3"
    )
    parser.add_argument("--prior-commit")
    parser.add_argument("--expected-version", default="0.5.4rc1")
    args = parser.parse_args(argv)
    for commit in (args.source_commit, args.prior_commit or PRIOR_COMMIT):
        if not re.fullmatch("[0-9a-f]{40}", commit):
            parser.error("Use full verified source commit identifiers.")
    if not (args.prior_source / "src/sinter/__init__.py").is_file():
        parser.error("Provide the extracted prior release source.")
    if not args.candidate_binary.is_file() or not os.access(
        args.candidate_binary, os.X_OK
    ):
        parser.error("Provide the actually installed candidate executable.")
    try:
        receipt = qualify(args)
    except (AssertionError, OSError, ValueError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Upgrade qualification failed: {error}\n")
    (args.output / "upgrade-test.json").write_text(
        json.dumps(receipt, indent=2), encoding="utf-8"
    )
    print("PASS: copied fictional prior workspace preserved by installed candidate.")


if __name__ == "__main__":
    main()
