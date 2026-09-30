"""Stage an explicitly qualified preview locally; never publish or move a tag."""

from __future__ import annotations

import argparse
import json
import shlex
import shutil
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


def _write_checksums(folder: Path) -> None:
    rows = [
        f"{digest(path)}  {name}"
        for name, path in sorted(_files(folder).items())
        if name != "SHA256SUMS.txt"
    ]
    (folder / "SHA256SUMS.txt").write_text("\n".join(rows) + "\n", encoding="ascii")


def release_notes(version: str, commit: str) -> str:
    """Keep public prose bound to the same qualified scope as its manifest."""
    if version == "0.5.4rc2":
        return _rc2_release_notes(commit)
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
        "unconfirmed owners, proposed dates and historical correspondence. "
        "Its eight\n"
        "named artifacts are bound to the installer and source in the "
        "qualification ZIP.\n"
        "No model operation was requested by this workflow; "
        "this is not live AI validation.",
    )
    return notes


def verify_plan(path: Path, repository: Path = ROOT) -> dict:
    """Validate a sealed candidate stage immediately before authorised publication."""
    plan = _json(path)
    version, commit = plan.get("version", ""), plan.get("source_commit", "")
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
                    or not name.startswith(("canonical/", "independent-review/"))
                ):
                    raise ValueError("The qualification ZIP contains unexpected paths.")
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


def publication_commands(manifest: Path) -> str:
    """Render the explicit post-approval commands; do not execute them."""
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
    args = parser.parse_args(argv)
    try:
        if args.operation == "prepare":
            path = prepare(
                args.candidate,
                args.independent_review,
                args.output,
                args.version,
                args.commit,
            )
            print(
                f"Prepared scoped candidate manifest: {path}; no publication performed."
            )
        elif args.operation == "verify":
            plan = verify_plan(args.manifest)
            print(
                f"Verified {plan['version']} at {plan['source_commit']}: "
                "Linux x64 only; no publication performed."
            )
        else:
            print(publication_commands(args.manifest), end="")
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
        zipfile.BadZipFile,
        tarfile.TarError,
    ) as error:
        parser.exit(1, f"{parser.prog}: candidate validation failed: {error}\n")


if __name__ == "__main__":
    main()
