"""Stage an explicitly qualified preview locally; never publish or move a tag."""

from __future__ import annotations

import argparse
import json
import os
import re
import shlex
import shutil
import stat
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from tools.candidate_qualification import (  # noqa: E402
    MAX_BUNDLE,
    MAX_FILE,
    REPOSITORY,
    REVIEW_FILES,
    SCHEMA,
    TARGET,
    UNQUALIFIED,
    _checksums,
    _files,
    _identity,
    _json,
    _safe_name,
    digest,
    verify_candidate,
)


def _manifest_for_dispatch(path: Path) -> dict:
    """Discover an exact RC4 profile; this read never grants release authority.

    RC4's finite inventory may exceed the legacy document limit. Discovery has
    the unchanged 64 MiB member bound, while every non-RC4 document still goes
    through the unchanged 2 MiB legacy reader before qualification can proceed.
    The fixed original authorizer independently rereads and pins RC4 bytes.
    """
    path = Path(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > MAX_FILE:
        raise ValueError("Candidate manifest is special or exceeds discovery bound.")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0)
    flags |= getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(path, flags)
    try:

        def identity(row):
            return (
                row.st_dev,
                row.st_ino,
                row.st_size,
                row.st_mtime_ns,
                row.st_ctime_ns,
            )

        opened = os.fstat(descriptor)
        if not stat.S_ISREG(opened.st_mode) or identity(before) != identity(opened):
            raise ValueError("Candidate manifest changed before discovery.")
        chunks, size = [], 0
        while chunk := os.read(descriptor, min(1024 * 1024, MAX_FILE + 1 - size)):
            size += len(chunk)
            if size > MAX_FILE:
                raise ValueError("Candidate manifest grew beyond discovery bound.")
            chunks.append(chunk)
        if (
            size != before.st_size
            or identity(before) != identity(os.fstat(descriptor))
            or identity(before) != identity(path.lstat())
        ):
            raise ValueError("Candidate manifest changed during discovery.")
    except BaseException as error:
        try:
            os.close(descriptor)
        except BaseException as cleanup_error:
            cleanup_errors = getattr(error, "manifest_cleanup_errors", ())
            error.manifest_cleanup_errors = cleanup_errors + (cleanup_error,)
            error.manifest_cleanup_error = cleanup_error
        raise
    else:
        os.close(descriptor)

    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Candidate manifest has a duplicate JSON field.")
            result[key] = value
        return result

    raw = b"".join(chunks)
    try:
        plan = json.loads(raw.decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeError, RecursionError) as error:
        raise ValueError("Candidate discovery requires bounded UTF-8 JSON.") from error
    if type(plan) is not dict:
        raise ValueError("Candidate discovery requires one JSON object.")
    if plan.get("version") != "0.5.4rc4":
        # This authoritative legacy call retains its exact original size bound,
        # schema, version policy and defaults; discovery is not size admission.
        return _json(path)

    from tools import rc4_candidate_release as rc4

    plan = rc4.strict_json(raw)
    expected = {
        "schema": rc4.SCHEMA,
        "version": rc4.VERSION,
        "repository": REPOSITORY,
        "tag": "v" + rc4.VERSION,
        "prerelease": True,
        "latest": False,
        "qualified_targets": [TARGET],
        "unqualified_targets": UNQUALIFIED,
        "all_platform_release_qualified": False,
        "publication_executed": False,
        "original_authorization_required": True,
        "historical_semantic_replay": False,
        "new_installed_execution": False,
    }
    if not all(
        type(plan.get(key)) is type(value) and plan[key] == value
        for key, value in expected.items()
    ) or not (
        type(plan.get("source_commit")) is str
        and re.fullmatch(r"[0-9a-f]{40}", plan["source_commit"])
    ):
        raise ValueError("Candidate discovery requires the exact RC4 identity/profile.")
    return plan


def _write_checksums(folder: Path) -> None:
    rows = [
        f"{digest(path)}  {name}"
        for name, path in sorted(_files(folder).items())
        if name != "SHA256SUMS.txt"
    ]
    (folder / "SHA256SUMS.txt").write_text("\n".join(rows) + "\n", encoding="ascii")


def release_notes(version: str, commit: str) -> str:
    """Keep public prose bound to the same qualified scope as its manifest."""
    if version == "0.5.4rc4":
        from tools.rc4_candidate_release import release_notes as rc4_notes

        return rc4_notes(commit)
    if version == "0.5.4rc2":
        return _rc2_release_notes(commit)
    if version == "0.5.4rc3":
        return _rc3_release_notes(commit)
    if version != "0.5.4rc1":
        raise ValueError("This candidate version has no explicit release notes policy.")
    status = (
        "This is a separate prerelease; the published v0.5.3 preview remains unchanged."
    )
    return f"""# Sinter {version} — Linux x64 preview

Exact source: `{commit}`. {status}

Only Linux x64 has installed qualification: Ubuntu 22.04/glibc 2.35, native execution,
with a clean offline install and actual v0.5.3 package replacement retaining a copied
fictional workspace, preferences, explicit model selection and saved source evidence.
The Debian package version is `{version.replace("rc", "~rc")}`.

The original qualification bundle and independent clean-install receipts are in
`sinter-{version}-qualification.zip`. SHA256SUMS and candidate-release-manifest.json
bind every uploaded asset. This separate scoped gate does not satisfy or bypass
the nine-platform release gate. Unqualified: {", ".join(UNQUALIFIED)}.

Local source inspection, editable campaigns, source-only casebooks/handover, saving,
export and restore do not require an API key, internet or a downloaded model.
The fictional walkthrough is `examples/offline-garden/README.md` in the source ZIP.

Optional native NeuroForge AI is restricted to its public qualified profile:
buffered text, 1–128 output tokens, a 2,048-byte final question, bounded recent
history and a separate 512-token prompt budget. Short source answer previews its
exact selected source. Long native recipes, caller system instructions, streaming,
tools, media and exact public token preflight are unsupported. Inputs and incomplete
results remain local; uncertain requests are never automatically replayed.
One useful fictional short source answer is recorded; general native assistant
quality and completed live ChatGPT generation are not qualified by this release.

These packages are unsigned and not notarised. Follow your organisation's policy;
never disable OS protections. Local work and backups are unencrypted. This is a
single trusted user's workbench, not hosted collaboration or an autonomous sender.
Customer-device acceptance and other-platform qualification remain outstanding.
"""


def _rc2_release_notes(commit: str) -> str:
    """Extend the next candidate's scope without rewriting frozen RC1 notes."""
    notes = release_notes("0.5.4rc1", commit)
    notes = notes.replace("Sinter 0.5.4rc1", "Sinter 0.5.4rc2")
    notes = notes.replace(
        "sinter-0.5.4rc1-qualification.zip", "sinter-0.5.4rc2-qualification.zip"
    )
    notes = notes.replace("`0.5.4~rc1`", "`0.5.4~rc2`")
    notes = notes.replace(
        "the published v0.5.3 preview remains unchanged.",
        "the published v0.5.3 and v0.5.4rc1 previews remain unchanged.",
    )
    notes = notes.replace(
        "with a clean offline install and actual v0.5.3 package replacement "
        "retaining a copied\n"
        "fictional workspace, preferences, explicit model selection and "
        "saved source evidence.",
        "with a clean offline install and separate actual v0.5.3 and "
        "published v0.5.4rc1\n"
        "package replacements retaining copied fictional workspaces, "
        "preferences, explicit\n"
        "model selection and saved source evidence.",
    )
    notes = notes.replace(
        "The fictional walkthrough is `examples/offline-garden/README.md` "
        "in the source ZIP.",
        "The fictional walkthrough is `examples/offline-garden/README.md` "
        "in the source ZIP.\n"
        "The installed offline browser qualification retains exact "
        "source navigation, edits,\n"
        "save/quit/restart/reopen, Word and JSON exports, "
        "separate restored copies and\n"
        "unconfirmed owners, proposed dates, saved correspondence drafts "
        "and historical records.\nIts eight\n"
        "named artifacts are bound to the installer and source in the "
        "qualification ZIP.\n"
        "No model operation was requested by this workflow; "
        "this is not live AI validation.",
    )
    return notes


def _rc3_release_notes(commit: str) -> str:
    """Describe this gate explicitly; never inherit an arbitrary preview claim."""
    return f"""# Sinter 0.5.4rc3 — Linux x64 preview

Exact source: `{commit}`. This is a separate prerelease; the published v0.5.3,
v0.5.4rc1 and v0.5.4rc2 previews remain unchanged.

Only Linux x64 has installed qualification: Ubuntu 22.04/glibc 2.35. The Debian
package version is `0.5.4~rc3`. Qualification requires a clean offline install and
separate actual package replacements from all three published priors, retaining
copied fictional workspaces, preferences, explicit model selection, historical
source snapshots, stale user reviews and unknown or unassigned owners.

The installed-workflow/v2 gate covers source inspection, source-only handover,
edits, save/quit/restart/reopen, Word and JSON exports and separate restored
copies. It requires the exact 53-operation installed catalogue and three actual
local Word copies: applied wording, changed wording and an unconfirmed save.
Pending edits remain protected; previous copies and saved records are retained,
and an uncertain save is not automatically replayed. These are fictional local
workflow checks; ordinary customer-browser download delivery remains unqualified.
Additional installed-recovery/v1 evidence binds held actions,
cold reopening, explicit resume, closed-route calendar exclusion, proposed dates
and complete stopped-process backup recovery to the exact installed binary.
Both clipboard and denied/unavailable clipboard manual-selection branches retain
the complete working document and restore distinct copies without rewriting the
saved original. Copying or selecting backup text does not save the project or
create a file. Oversized backup capture above saved-work limits is not certified
as an installed restore. Older previews cannot open backups containing On hold;
keep an unchanged older workspace copy if you need to return to an older preview.

`sinter-0.5.4rc3-qualification.zip` contains the original qualification bundle and
independent clean-install receipts. SHA256SUMS and candidate-release-manifest.json
bind every uploaded asset. This scoped gate does not satisfy or bypass the
nine-platform release gate. Unqualified: {", ".join(UNQUALIFIED)}.

Local work does not require an API key, internet or a downloaded model. The
fictional walkthrough is `examples/offline-garden/README.md` in the source ZIP.
No model operation was requested by these installed workflows. Native NeuroForge
AI remains an optional qualified public profile with buffered text, 1–128 output
tokens, a 2,048-byte final question, bounded recent history and a 512-token prompt
budget. Long native recipes, system instructions, streaming, tools, media and
exact public token preflight are unsupported. General native assistant quality
and completed live ChatGPT generation are not qualified by this release.
Inputs and incomplete results remain local; uncertain requests are never replayed
automatically.

These packages are unsigned and not notarised. Follow your organisation's policy;
never disable OS protections. Local work and backups are unencrypted. This is a
single trusted user's workbench, not hosted collaboration or an autonomous sender.
Customer-device acceptance and other-platform qualification remain outstanding.
"""


def verify_plan(
    path: Path,
    repository: Path = ROOT,
    *,
    rc4_context=None,
    rc4_pins=None,
    rc4_manifest_sha256=None,
) -> dict:
    """Validate a sealed candidate stage immediately before authorised publication."""
    plan = _manifest_for_dispatch(path)
    version, commit = plan.get("version", ""), plan.get("source_commit", "")
    if version == "0.5.4rc4":
        from tools.rc4_candidate_release import authorize_original

        return authorize_original(
            path,
            context=rc4_context,
            pins=rc4_pins,
            manifest_sha256=rc4_manifest_sha256,
        )
    _identity(version, commit)
    if (
        plan.get("schema") != SCHEMA
        or plan.get("repository") != REPOSITORY
        or plan.get("tag") != f"v{version}"
        or plan.get("prerelease") is not True
        or plan.get("latest") is not False
        or plan.get("qualified_targets") != [TARGET]
        or plan.get("unqualified_targets") != UNQUALIFIED
        or plan.get("all_platform_release_qualified") is not False
        or plan.get("human_approval_required") is not True
        or plan.get("publication_executed") is not False
    ):
        raise ValueError(
            "The publication plan does not preserve scoped prerelease limits."
        )
    if path.name != "candidate-release-manifest.json":
        raise ValueError("Use the sealed candidate-release-manifest.json.")
    folder = path.parent
    sums = _checksums(folder)
    if (folder / "RELEASE-NOTES.md").read_text(encoding="utf-8") != release_notes(
        version, commit
    ):
        raise ValueError("The release notes differ from the qualified preview scope.")
    assets = plan.get("assets", [])
    public_names = {
        f"Sinter-{version}-linux-x64.deb",
        f"Sinter-{version}-linux-x64.tar.gz",
        f"sinter-{version}-source.zip",
        f"sinter-{version}.pyz",
        f"sinter-{version}-qualification.zip",
        "RELEASE-NOTES.md",
    }
    if (
        not isinstance(assets, list)
        or any(not isinstance(row, dict) for row in assets)
        or len(assets) != len({row.get("path") for row in assets})
        or {row.get("path") for row in assets} != public_names
        or public_names != set(sums) - {path.name}
    ):
        raise ValueError("The publication plan does not cover its exact staged assets.")
    for row in assets:
        if (
            row.get("sha256") != sums[row["path"]]
            or type(row.get("bytes")) is not int
            or row["bytes"] != (folder / row["path"]).stat().st_size
        ):
            raise ValueError(
                "A staged publication asset differs from its sealed identity."
            )
    with tempfile.TemporaryDirectory(prefix="sinter-candidate-check-") as temporary:
        target = Path(temporary)
        total = 0
        with zipfile.ZipFile(folder / f"sinter-{version}-qualification.zip") as bundle:
            seen = set()
            for row in bundle.infolist():
                name = _safe_name(row.filename)
                if (
                    name in seen
                    or row.is_dir()
                    or stat.S_IFMT(row.external_attr >> 16) not in {0, stat.S_IFREG}
                    or row.external_attr & 0x10
                    or not name.startswith(("canonical/", "independent-review/"))
                ):
                    raise ValueError(
                        "The qualification ZIP contains unexpected paths "
                        "or entry types."
                    )
                seen.add(name)
                total += row.file_size
                if row.file_size > MAX_FILE or total > MAX_BUNDLE:
                    raise ValueError("The qualification ZIP exceeds its bound.")
                destination = target / name
                destination.parent.mkdir(parents=True, exist_ok=True)
                destination.write_bytes(bundle.read(row))
        canonical = target / "canonical"
        if set(_files(target / "independent-review")) != set(REVIEW_FILES):
            raise ValueError(
                "The independent review bundle has missing or unexpected files."
            )
        result = verify_candidate(
            canonical, target / "independent-review", version, commit, repository
        )
        for name in (
            f"Sinter-{version}-linux-x64.deb",
            f"Sinter-{version}-linux-x64.tar.gz",
            f"sinter-{version}-source.zip",
            f"sinter-{version}.pyz",
        ):
            if digest(canonical / name) != digest(folder / name):
                raise ValueError(
                    "A public download differs from its qualification bundle."
                )
    if plan.get("verification") != result:
        raise ValueError("The publication verification summary differs.")
    return plan


def prepare(
    folder: Path,
    review: Path,
    output: Path,
    version: str,
    commit: str,
    repository: Path = ROOT,
    *,
    rc4_context=None,
    rc4_pins=None,
) -> Path:
    """Create a new reviewable stage while leaving canonical artifacts untouched."""
    if (
        output.exists()
        or output.resolve().is_relative_to(folder.resolve())
        or output.resolve().is_relative_to(review.resolve())
    ):
        raise ValueError(
            "Choose a new staging directory; existing bundles are never overwritten."
        )
    if version == "0.5.4rc4":
        from tools.rc4_candidate_release import (
            OriginalContext,
            OriginalPins,
            prepare_original,
        )

        if (
            type(rc4_context) is not OriginalContext
            or type(rc4_pins) is not OriginalPins
            or rc4_context.candidate != folder
            or rc4_context.independent_review != review
            or rc4_context.repository != repository
            or rc4_pins.source_commit != commit
        ):
            raise ValueError(
                "RC4 staging requires its explicit original context and independently trusted pins."
            )
        return prepare_original(rc4_context, output, rc4_pins)
    result = verify_candidate(folder, review, version, commit, repository)
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix="sinter-candidate-stage-", dir=output.parent
    ) as temporary:
        stage = Path(temporary)
        products = [
            f"Sinter-{version}-linux-x64.deb",
            f"Sinter-{version}-linux-x64.tar.gz",
            f"sinter-{version}-source.zip",
            f"sinter-{version}.pyz",
        ]
        for name in products:
            shutil.copyfile(folder / name, stage / name)
        with zipfile.ZipFile(
            stage / f"sinter-{version}-qualification.zip",
            "w",
            compression=zipfile.ZIP_DEFLATED,
        ) as bundle:
            for name, path in sorted(_files(folder).items()):
                bundle.write(path, "canonical/" + name)
            for name in REVIEW_FILES:
                bundle.write(review / name, "independent-review/" + name)
        notes = release_notes(version, commit)
        (stage / "RELEASE-NOTES.md").write_text(notes, encoding="utf-8")
        assets = [
            {"path": name, "sha256": digest(path), "bytes": path.stat().st_size}
            for name, path in sorted(_files(stage).items())
        ]
        plan = {
            "schema": SCHEMA,
            "version": version,
            "source_commit": commit,
            "repository": REPOSITORY,
            "tag": f"v{version}",
            "prerelease": True,
            "latest": False,
            "qualified_targets": [TARGET],
            "unqualified_targets": UNQUALIFIED,
            "all_platform_release_qualified": False,
            "human_approval_required": True,
            "publication_executed": False,
            "verification": result,
            "assets": assets,
        }
        manifest = stage / "candidate-release-manifest.json"
        manifest.write_text(json.dumps(plan, indent=2) + "\n", encoding="utf-8")
        _write_checksums(stage)
        verify_plan(manifest, repository)
        stage.rename(output)
    return output / "candidate-release-manifest.json"


def publication_commands(
    manifest: Path,
    *,
    rc4_context=None,
    rc4_pins=None,
    rc4_manifest_sha256=None,
    rc4_authorization_files=None,
) -> str:
    """Render the explicit post-approval commands; do not execute them."""
    if any(value is not None for value in (rc4_context, rc4_pins, rc4_manifest_sha256)):
        plan = verify_plan(
            manifest,
            rc4_context=rc4_context,
            rc4_pins=rc4_pins,
            rc4_manifest_sha256=rc4_manifest_sha256,
        )
    else:
        plan = verify_plan(manifest)
    files = [manifest.parent / row["path"] for row in plan["assets"]]
    files += [manifest, manifest.parent / "SHA256SUMS.txt"]
    tag = [
        "python3",
        "tools/release_tag.py",
        "--repository",
        plan["repository"],
        "--tag",
        plan["tag"],
        "--commit",
        plan["source_commit"],
        "--candidate-manifest",
        str(manifest),
    ]
    if plan["version"] == "0.5.4rc4":
        tag.insert(1, "-B")
        if type(rc4_authorization_files) is not dict or set(
            rc4_authorization_files
        ) != {
            "original-context",
            "original-context-sha256",
            "trusted-pins",
            "trusted-pins-sha256",
            "manifest-sha256",
        }:
            raise ValueError(
                "RC4 publication commands require exact externally pinned original authorization files."
            )
        from tools.rc4_candidate_release import load_original

        supplied_context, supplied_pins = load_original(
            rc4_authorization_files["original-context"],
            rc4_authorization_files["original-context-sha256"],
            rc4_authorization_files["trusted-pins"],
            rc4_authorization_files["trusted-pins-sha256"],
        )
        if (
            supplied_context,
            supplied_pins,
            rc4_authorization_files["manifest-sha256"],
        ) != (rc4_context, rc4_pins, rc4_manifest_sha256):
            raise ValueError(
                "Rendered RC4 tag commands name different original authorization inputs."
            )
        for name, value in rc4_authorization_files.items():
            tag += ["--" + name, str(value)]
    release = [
        "gh",
        "release",
        "create",
        plan["tag"],
        *map(str, files),
        "--repo",
        plan["repository"],
        "--verify-tag",
        "--prerelease",
        "--latest=false",
        "--title",
        f"Sinter {plan['version']} — Linux x64 preview",
        "--notes-file",
        str(manifest.parent / "RELEASE-NOTES.md"),
    ]
    return (
        "# Run only after human approval of this exact manifest and asset hashes.\n"
        + shlex.join(tag)
        + "\n"
        + shlex.join(release)
        + "\n"
    )


def main(argv: list[str] | None = None) -> None:
    """Handle local staging and verification only; no network action exists."""
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    stage = commands.add_parser(
        "prepare", help="Verify a frozen Linux x64 rc bundle and stage it locally."
    )
    for name in ("candidate", "independent-review", "output"):
        stage.add_argument("--" + name, type=Path, required=True)
    stage.add_argument("--version", required=True)
    stage.add_argument("--commit", required=True)
    verify = commands.add_parser(
        "verify", help="Recheck every artifact in an existing sealed stage."
    )
    verify.add_argument("manifest", type=Path)
    render = commands.add_parser(
        "commands", help="Print publication commands for human review; never run them."
    )
    render.add_argument("manifest", type=Path)
    for command in (stage, verify, render):
        command.add_argument("--original-context", type=Path)
        command.add_argument("--original-context-sha256")
        command.add_argument("--trusted-pins", type=Path)
        command.add_argument("--trusted-pins-sha256")
        command.add_argument("--manifest-sha256")
    args = parser.parse_args(argv)
    try:
        version = (
            args.version
            if args.operation == "prepare"
            else _manifest_for_dispatch(args.manifest).get("version")
        )
        rc4 = {}
        if version == "0.5.4rc4":
            from tools.rc4_candidate_release import load_original

            if not all(
                (
                    args.original_context,
                    args.original_context_sha256,
                    args.trusted_pins,
                    args.trusted_pins_sha256,
                )
            ):
                raise ValueError(
                    "RC4 requires explicit original context and trusted pins with independent file hashes."
                )
            context, pins = load_original(
                args.original_context,
                args.original_context_sha256,
                args.trusted_pins,
                args.trusted_pins_sha256,
            )
            rc4 = {"rc4_context": context, "rc4_pins": pins}
            if args.operation == "prepare":
                rc4["repository"] = context.repository
            if args.operation != "prepare":
                rc4["rc4_manifest_sha256"] = args.manifest_sha256
        if args.operation == "prepare":
            path = prepare(
                args.candidate,
                args.independent_review,
                args.output,
                args.version,
                args.commit,
                **rc4,
            )
            print(
                f"Prepared scoped candidate manifest: {path}; no publication performed."
            )
        elif args.operation == "verify":
            plan = verify_plan(args.manifest, **rc4)
            print(
                f"Verified {plan['version']} at {plan['source_commit']}: "
                "Linux x64 only; no publication performed."
            )
        else:
            if rc4:
                rc4["rc4_authorization_files"] = {
                    "original-context": args.original_context,
                    "original-context-sha256": args.original_context_sha256,
                    "trusted-pins": args.trusted_pins,
                    "trusted-pins-sha256": args.trusted_pins_sha256,
                    "manifest-sha256": args.manifest_sha256,
                }
            print(publication_commands(args.manifest, **rc4), end="")
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        ImportError,
        subprocess.SubprocessError,
        zipfile.BadZipFile,
        tarfile.TarError,
    ) as error:
        parser.exit(1, f"{parser.prog}: candidate validation failed: {error}\n")


if __name__ == "__main__":
    main()
