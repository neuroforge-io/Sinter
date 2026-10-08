"""Stage and authorise exact RC4 originals; public inspection is integrity only.

This module never installs, builds, publishes or creates a tag. Qualification
requires the original closed evidence trees and separately supplied trusted pins.
An exported catalogue cannot substitute for those original semantic gates.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import json
import os
import re
import shutil
import stat
import sys
import tarfile
import tempfile
import zipfile
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
from tools import candidate_qualification as legacy  # noqa: E402
from tools import rc4_evidence_catalog as transport  # noqa: E402

VERSION = "0.5.4rc4"
SCHEMA = "sinter-original-rc4-candidate-release/v1"
PINS_SCHEMA = "sinter-original-rc4-trusted-pins/v1"
CONTEXT_SCHEMA = "sinter-original-rc4-context/v1"
PUBLIC_SCHEMA = "sinter-rc4-public-integrity-inspection/v1"
AUTHORIZATION_SCHEMA = "sinter-rc4-original-release-authorization/v1"
REVIEW_SCHEMA = "sinter-independent-rc4-final-artifact-review/v1"
MAX_FILE = transport.MAX_MEMBER
MAX_BUNDLE = transport.MAX_TOTAL
SCOPES = (
    "candidate",
    "independent-review",
    "workflow",
    "recovery",
    "native",
    "replacement",
    "replacement-candidate",
    "priors",
)
REQUIRED_TOOLS = (
    "tools/rc4_candidate_release.py",
    "tools/rc4_installed_workflow.py",
    "tools/rc4_installed_workflow_contract.py",
    "tools/rc4_installed_recovery.py",
    "tools/rc4_installed_recovery_contract.py",
    "tools/rc4_native_handoff.py",
    "tools/rc4_native_handoff_contract.py",
    "tools/rc4_replacement.py",
    "tools/rc4_replacement_contract.py",
    "tools/rc4_host_tools.py",
)
REVIEW_CHECKS = legacy.independent_review_checks("0.5.4rc3") + (
    "rc4_exact_original_source_catalogue_22_checks_13_roles",
    "rc4_original_installed_recovery_both_profiles",
    "rc4_original_native_four_launches_and_fresh_handoff",
    "rc4_original_four_exact_published_prior_replacements",
    "rc4_actual_before_and_after_host_tool_observations",
)


def require(value, message):
    if not value:
        raise ValueError(message)


def canonical(value):
    return (
        json.dumps(
            value,
            sort_keys=True,
            ensure_ascii=True,
            allow_nan=False,
            separators=(",", ":"),
        )
        + "\n"
    ).encode("utf-8")


def sha(raw):
    return hashlib.sha256(raw).hexdigest()


def strict_json(raw):
    return transport._json(raw)


def regular(path, limit=MAX_FILE):
    path = Path(path).absolute()
    tree = transport._Tree(path.parent)
    with tree.root_fd() as descriptor:
        raw = tree.read(descriptor, path.name)
    require(
        type(limit) is int and 0 <= limit <= MAX_FILE and len(raw) <= limit,
        "A retained file exceeds its explicit unchanged member limit.",
    )
    return raw


def _asset_bytes(path):
    path = Path(path).absolute()
    if path.name != f"sinter-{VERSION}-qualification.zip":
        return regular(path)
    # The outer encoded archive is not a transport member. Legacy policy bounds
    # every expanded member at 64 MiB and the expanded bundle at 256 MiB; do not
    # impose an accidental 64 MiB bound on the complete uploaded ZIP container.
    tree = transport._Tree(path.parent)
    with tree.root_fd() as parent, transport._descriptors() as opened:
        before = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        require(
            stat.S_ISREG(before.st_mode)
            and before.st_nlink == 1
            and before.st_size <= MAX_BUNDLE,
            "The outer qualification archive is redirected, special or over bound.",
        )
        descriptor = os.open(path.name, transport._FILE_FLAGS, dir_fd=parent)
        opened.append(descriptor)
        actual = os.fstat(descriptor)
        identity = lambda row: (
            row.st_dev,
            row.st_ino,
            row.st_size,
            row.st_mtime_ns,
            row.st_ctime_ns,
        )
        require(
            identity(before) == identity(actual),
            "The outer qualification archive changed before opening.",
        )
        chunks, size = [], 0
        while chunk := os.read(descriptor, min(1024 * 1024, MAX_BUNDLE + 1 - size)):
            size += len(chunk)
            require(
                size <= MAX_BUNDLE, "The outer qualification archive grew beyond bound."
            )
            chunks.append(chunk)
        after = os.fstat(descriptor)
        final = os.stat(path.name, dir_fd=parent, follow_symlinks=False)
        require(
            size == before.st_size
            and identity(before) == identity(after) == identity(final),
            "The complete outer qualification archive changed during inspection.",
        )
        return b"".join(chunks)


def record(raw):
    return {"bytes": len(raw), "sha256": sha(raw)}


@dataclass(frozen=True)
class OriginalPins:
    source_commit: str
    source_archive_sha256: str
    tool_manifest_sha256: str
    installer_sha256: str
    package_receipt_sha256: str
    native_archive_sha256: str
    portable_sha256: str
    native_binary_sha256: str
    independent_review_sha256: str
    chromium_sha256: str
    image_id: str

    def validate(self):
        require(
            type(self.source_commit) is str
            and re.fullmatch(r"[0-9a-f]{40}", self.source_commit),
            "Use a full externally reviewed final source commit.",
        )
        for key, value in asdict(self).items():
            if key in {"source_commit", "image_id"}:
                continue
            require(
                type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value),
                "Every final source/tool/package/binary/review pin must be explicit SHA-256.",
            )
        require(
            type(self.image_id) is str
            and re.fullmatch(r"sha256:[0-9a-f]{64}", self.image_id),
            "Use the exact qualified offline image pin.",
        )


@dataclass(frozen=True)
class OriginalContext:
    repository: Path
    candidate: Path
    independent_review: Path
    workflow: Path
    recovery: Path
    native: Path
    replacement: Path
    priors: Path
    replacement_owned_root: Path
    replacement_candidate: Path
    replacement_repository: Path
    chromium: Path

    def roots(self):
        return {scope: getattr(self, scope.replace("-", "_")) for scope in SCOPES}


def _load_external(path, expected, schema, kind):
    raw = regular(path)
    require(
        type(expected) is str
        and re.fullmatch(r"[0-9a-f]{64}", expected)
        and sha(raw) == expected,
        "External context or trusted-pin bytes differ from their explicit pin.",
    )
    value = strict_json(raw)
    require(
        set(value) == {"schema", *kind.__dataclass_fields__}
        and value["schema"] == schema,
        "Original authorization input fields differ.",
    )
    fields = {key: value[key] for key in kind.__dataclass_fields__}
    require(
        all(
            type(item) is str and item and "\x00" not in item
            for item in fields.values()
        ),
        "Original authorization labels must be explicit strings.",
    )
    if kind is OriginalContext:
        fields = {key: Path(item) for key, item in fields.items()}
        require(
            all(item.is_absolute() for item in fields.values()),
            "Original context requires explicit absolute trusted labels.",
        )
    result = kind(**fields)
    if kind is OriginalPins:
        result.validate()
    return result


def load_original(context_file, context_sha256, pins_file, pins_sha256):
    return (
        _load_external(context_file, context_sha256, CONTEXT_SCHEMA, OriginalContext),
        _load_external(pins_file, pins_sha256, PINS_SCHEMA, OriginalPins),
    )


def product_names():
    return (
        f"Sinter-{VERSION}-linux-x64.deb",
        f"Sinter-{VERSION}-linux-x64.tar.gz",
        f"sinter-{VERSION}-source.zip",
        f"sinter-{VERSION}.pyz",
    )


def _inventory(root, *, encoded_stage=False):
    tree = transport._Tree(Path(root))
    files, directories, pending = {}, [], [""]
    with tree.root_fd() as root_fd:
        while pending:
            directory = pending.pop()
            sentinel = directory + "/unused" if directory else "unused"
            with tree.parent_fd(root_fd, sentinel) as descriptor:
                with os.scandir(descriptor) as entries:
                    names = sorted(entry.name for entry in entries)
                for leaf in names:
                    relative = directory + "/" + leaf if directory else leaf
                    legacy._safe_name(relative)
                    observed = os.stat(leaf, dir_fd=descriptor, follow_symlinks=False)
                    if stat.S_ISDIR(observed.st_mode):
                        directories.append(relative)
                        pending.append(relative)
                    elif stat.S_ISREG(observed.st_mode):
                        if (
                            encoded_stage
                            and not directory
                            and leaf == f"sinter-{VERSION}-qualification.zip"
                        ):
                            files[relative] = record(_asset_bytes(Path(root) / leaf))
                        else:
                            files[relative] = record(tree.read(root_fd, relative))
                    else:
                        raise ValueError(
                            "Original evidence contains a redirect or special entry."
                        )
    require(files, "An original raw gate inventory is empty.")
    return {"files": dict(sorted(files.items())), "directories": sorted(directories)}


def _inventories(context):
    require(
        type(context) is OriginalContext,
        "Use an explicit original authorization context.",
    )
    require(
        all(
            type(path) is type(Path())
            and path.is_absolute()
            and "\x00" not in str(path)
            for path in asdict(context).values()
        ),
        "Every original context label must be an explicit builtin absolute host Path.",
    )
    roots = context.roots()
    resolved = [str(path.resolve(strict=True)) for path in roots.values()]
    require(
        len(resolved) == len(set(resolved)),
        "Different semantic gates cannot reuse one evidence root.",
    )
    return {scope: _inventory(root) for scope, root in roots.items()}


def tool_manifest(source):
    return sha(
        canonical(
            {
                name: record(raw)
                for name, raw in sorted(source.items())
                if name.startswith("tools/") and name.endswith(".py")
            }
        )
    )


def _tools(source, pins):
    require(
        all(name in source for name in REQUIRED_TOOLS),
        "The final source lacks a required reviewed RC4 gate; no stage or tag can be authorised.",
    )
    require(
        tool_manifest(source) == pins.tool_manifest_sha256,
        "The independently pinned complete tool manifest differs.",
    )
    _source_tree(ROOT, source)
    for name, raw in source.items():
        if name.startswith(("tools/", "src/")) and name.endswith(
            (".py", ".js", ".css", ".html")
        ):
            require(
                regular(ROOT / name) == raw,
                "A running trusted verifier/product tool differs from the exact final source.",
            )


def _source_tree(root, source):
    observed = _inventory(root)
    require(
        observed["files"] == {name: record(raw) for name, raw in source.items()},
        "An executable gate source tree differs from the complete trusted final source.",
    )


def _review(context, pins, receipt):
    files = _inventory(context.independent_review)["files"]
    require(
        set(files) == set(legacy.REVIEW_FILES),
        "Independent review must retain its exact four original raw files.",
    )
    raw = regular(context.independent_review / "final-artifact-review.json")
    require(
        sha(raw) == pins.independent_review_sha256,
        "The independent review differs from its external trusted pin.",
    )
    independent = strict_json(raw)
    require(
        independent.get("schema") == REVIEW_SCHEMA
        and independent.get("version") == VERSION
        and independent.get("source_commit") == pins.source_commit,
        "The independent review has another source or candidate identity.",
    )
    checks = independent.get("checks")
    require(
        type(checks) is dict
        and set(checks) == set(REVIEW_CHECKS)
        and all(type(value) is bool and value for value in checks.values()),
        "An independent final artifact/installed gate review is incomplete.",
    )
    for key in (
        "installer_sha256",
        "native_archive_sha256",
        "source_archive_sha256",
        "portable_sha256",
        "native_binary_sha256",
        "tool_manifest_sha256",
    ):
        require(
            independent.get(key) == getattr(pins, key),
            "The independent final review tested different actual bytes.",
        )
    retained = independent.get("raw_files")
    require(
        type(retained) is dict and set(retained) == set(legacy.REVIEW_FILES[1:]),
        "Exact independent raw evidence identity rows are required.",
    )
    for name in legacy.REVIEW_FILES[1:]:
        require(
            retained.get(name) == files[name],
            "Complete independent clean-install raw evidence is not bound.",
        )
    clean = strict_json(
        regular(context.independent_review / "clean-ubuntu-installed-test.json")
    )
    require(
        clean == receipt["installed_test"],
        "The independent actual installed result differs from the package receipt.",
    )
    details = strict_json(
        regular(context.independent_review / "qualification-context.json")
    )
    required = {
        "source_commit": pins.source_commit,
        "version": VERSION,
        "installer_sha256": pins.installer_sha256,
        "container": "ubuntu:22.04",
        "network": "disabled",
        "host_installation": False,
        "product_edits": False,
        "preinstalled_python": False,
        "preinstalled_account_packages": False,
    }
    require(
        all(
            type(details.get(key)) is type(value) and details[key] == value
            for key, value in required.items()
        ),
        "Independent clean installation scope is not established.",
    )
    require(
        files["clean-ubuntu-installed-test.log"]["bytes"] > 0,
        "Complete independent installed command output is missing.",
    )


def verify_original(context, pins):
    """Rerun fixed original-tree semantic verifiers; never consume admission flags.

    No arbitrary callback, receipt-selected module or exported archive is executed.
    Imported verifier code is checked against the independently pinned final source
    before any gate is called. Missing final adapters and DEV source fail closed.
    """
    require(type(pins) is OriginalPins, "Use independently trusted final pins.")
    pins.validate()
    before = _inventories(context)
    names = product_names()
    expected = (
        pins.installer_sha256,
        pins.native_archive_sha256,
        pins.source_archive_sha256,
        pins.portable_sha256,
    )
    for name, digest in zip(names, expected):
        require(
            before["candidate"]["files"].get(name, {}).get("sha256") == digest,
            "A final product asset differs from its external trusted pin.",
        )
    receipt_name = f"Sinter-{VERSION}-linux-x64-test.json"
    require(
        before["candidate"]["files"].get(receipt_name, {}).get("sha256")
        == pins.package_receipt_sha256,
        "The actual package receipt differs from its external pin.",
    )
    replacement_candidate = before["replacement-candidate"]["files"]
    require(
        set(replacement_candidate) == {names[0], receipt_name}
        and replacement_candidate[names[0]]["sha256"] == pins.installer_sha256
        and replacement_candidate[receipt_name]["sha256"]
        == pins.package_receipt_sha256,
        "The actual replacement candidate mount is not the same final two pinned files.",
    )
    source = legacy._source(
        context.candidate, VERSION, pins.source_commit, context.repository
    )
    _tools(source, pins)
    from tools.installed_workflow_qualification import source_operations

    operations_count = len(source_operations(source))
    for path in (
        context.workflow / "source",
        context.recovery / "source",
        context.native / "baseline/source",
        context.native / "handoff-container/source",
    ):
        _source_tree(path, source)
    from tools.release_manifest import verify_target_receipt

    receipt = verify_target_receipt(
        context.candidate / receipt_name, context.candidate, pins.source_commit, VERSION
    )
    require(
        receipt.get("execution") == "native"
        and receipt.get("system", "").lower() == "linux"
        and receipt.get("target_arch") == "x64"
        and receipt.get("machine") == "x86_64"
        and type(receipt.get("pointer_bits")) is int
        and receipt["pointer_bits"] == 64
        and receipt.get("signed_by_publisher") is False,
        "Only the exact unsigned installed Linux x64 target can be admitted.",
    )
    binary = legacy._native_payload(context.candidate, VERSION, source, receipt)
    require(
        binary == pins.native_binary_sha256,
        "The actual DEB/native runtime binary differs from the independent final pin.",
    )
    legacy.verify_rc3_terminal_notices(context.candidate, receipt)
    inventory = strict_json(
        regular(context.candidate / "licenses/bundled-dependencies.json")
    )
    require(
        inventory.get("schema") == "sinter-native-dependencies/v1"
        and inventory.get("packages") == receipt["bundled_dependencies"]
        and inventory.get("account_auth_bundled") is True
        and inventory.get("linux_shared_library_notices_verified") is True,
        "Complete exported dependency/notice bytes differ from the actual installed inventory.",
    )
    _review(context, pins, receipt)
    # These imports are fixed trusted source modules. They are deliberately absent
    # in incomplete DEV trees: an incomplete adapter is never an accepting route.
    from tools import installed_native_container as owner
    from tools.rc4_host_tools import validate_host_pair
    from tools.rc4_installed_recovery import verify as recovery_verify
    from tools.rc4_installed_workflow_contract import verify_original as workflow_verify
    from tools.rc4_native_handoff_contract import verify as native_verify
    from tools.rc4_replacement_contract import PRIORS
    from tools.rc4_replacement_contract import verify as replacement_verify

    require(
        pins.image_id == owner.IMAGE_ID, "The qualified immutable image pin differs."
    )
    common = {
        "source_commit": pins.source_commit,
        "installer_sha256": pins.installer_sha256,
        "package_receipt_sha256": pins.package_receipt_sha256,
    }
    workflow = workflow_verify(
        SimpleNamespace(
            proof_root=context.workflow,
            owner_sha256=sha(source["tools/rc4_installed_workflow.py"]),
            **common,
        )
    )
    recovery = recovery_verify(
        SimpleNamespace(
            proof_root=context.recovery,
            owner_sha256=sha(source["tools/rc4_installed_recovery.py"]),
            **common,
        )
    )
    native = native_verify(
        SimpleNamespace(
            output=context.native,
            repository=context.repository,
            installer=context.candidate / names[0],
            package_receipt=context.candidate / receipt_name,
            source_commit=pins.source_commit,
            owner_sha256=sha(source[owner.SOURCE_FILE]),
            qualification="candidate",
            chromium_sha256=pins.chromium_sha256,
        )
    )
    replacement = replacement_verify(
        SimpleNamespace(
            repository=context.replacement_repository,
            candidate=context.replacement_candidate,
            priors=context.priors,
            output=context.replacement,
            outer_owner_file=ROOT / "tools/rc4_replacement.py",
            owned_root=context.replacement_owned_root,
            chromium=context.chromium,
            source_commit=pins.source_commit,
            image_id=pins.image_id,
            outer_owner_sha256=sha(source["tools/rc4_replacement.py"]),
        )
    )
    require(
        workflow.get("schema") == "sinter-owned-rc4-installed-workflow-admission/v1"
        and workflow.get("source_commit") == pins.source_commit
        and workflow.get("version") == VERSION
        and workflow.get("installer_sha256") == pins.installer_sha256
        and workflow.get("package_receipt_sha256") == pins.package_receipt_sha256
        and workflow.get("binary_sha256") == pins.native_binary_sha256
        and workflow.get("app_lifetimes") == 2
        and type(workflow.get("operations_catalogue")) is int
        and workflow.get("operations_catalogue") == operations_count
        and workflow.get("named_checks") == 22
        and workflow.get("workflow_roles") == 13
        and recovery.get("candidate_commit") == pins.source_commit
        and recovery.get("boundary") == "candidate"
        and recovery.get("installed_lifetimes") == 10
        and native.get("source_commit") == pins.source_commit
        and native.get("version") == VERSION
        and native.get("qualification") == "candidate"
        and native.get("installer_sha256") == pins.installer_sha256
        and native.get("baseline", {}).get("binary_sha256") == pins.native_binary_sha256
        and replacement.get("source_commit") == pins.source_commit
        and replacement.get("candidate_installer_sha256") == pins.installer_sha256,
        "Actual installed gates do not bind one final source/package/binary identity.",
    )
    require(
        set(PRIORS) == {"0.5.3", "0.5.4rc1", "0.5.4rc2", "0.5.4rc3"},
        "All four exact published prior policies, including published E, are required.",
    )
    for version in PRIORS:
        raw = strict_json(regular(context.replacement / version / "outer.json"))
        require(
            raw.get("schema") == "sinter-rc4-replacement-owner/v2",
            "The original replacement lacks mandatory actual before/after host evidence.",
        )
        validate_host_pair(raw["host"])
    handoff = strict_json(regular(context.native / "handoff-container/browser.json"))
    require(
        handoff.get("schema") == "sinter-rc4-native-handoff-browser/v3",
        "The native handoff lacks actual after fingerprints and owned temp evidence.",
    )
    require(
        _inventories(context) == before,
        "A complete original raw evidence tree changed during semantic revalidation.",
    )
    return {
        "schema": AUTHORIZATION_SCHEMA,
        "version": VERSION,
        "source_commit": pins.source_commit,
        "qualified_target": legacy.TARGET,
        "original_semantic_gates_revalidated": True,
        "new_installed_execution": False,
        "gates": {
            "workflow": workflow,
            "recovery": recovery,
            "native": native,
            "replacement": replacement,
        },
        "product_runtime_and_notices_verified": True,
        "independent_clean_install_review_verified": True,
        "unqualified_targets": legacy.UNQUALIFIED,
        "all_platform_release_qualified": False,
        "general_ai_quality_qualified": False,
        "customer_device_acceptance": False,
    }


def release_notes(commit, *, operations_catalogue=None):
    require(
        type(commit) is str and re.fullmatch(r"[0-9a-f]{40}", commit),
        "Use the exact final source commit.",
    )
    require(
        operations_catalogue is None
        or type(operations_catalogue) is int
        and operations_catalogue in {53, 54},
        "Only the source-declared 53 or 54 operation catalogue is supported.",
    )
    catalogue = (
        "the exact source-declared 53-entry legacy or recognized 54-entry funding catalogue"
        if operations_catalogue is None
        else f"the exact {operations_catalogue}-entry source-declared operation catalogue"
    )
    return f"""# Sinter {VERSION} — Linux x64 preview

Exact source: `{commit}`. This separate prerelease leaves v0.5.3 and all previous
previews unchanged. Linux x64 only: Ubuntu 22.04/glibc 2.35, Debian version
`0.5.4~rc4`. The original qualification requires clean offline installation,
{catalogue}, 22 named UI checks and 13 artifact roles,
both installed recovery profiles, four native entry launches plus a fresh browser
handoff, and four separate actual replacements of the published prior previews.
The installed CLI catalogue is compared with the complete trusted source contract;
this does not claim that every catalogue operation was executed through the UI.
The copied fictional sources, historical records, explicit saved model selection,
unknown and unassigned owners, proposed dates, uncertain edits, original wording
and separate restored copies are retained. Uncertain operations are not replayed
automatically. Local workflows require no API key, internet or downloaded model.

The qualification ZIP is a finite export of the actual original evidence,
product runtime/notice identities and independent clean-install review. Public
inspection checks externally pinned exported bytes only; historical semantic
replay and new installed execution are explicitly false. Publication authorization
requires the original environment and reruns its exact semantic gates. Host
Docker, Python, Chromium and Playwright Node remain an explicit external trust
boundary with actual before/after observations; their executable bytes are not
included in the evidence bundle.

Optional native NeuroForge AI supports its public buffered profile only: 1–128
output tokens, a 2,048-byte final question, bounded recent history and a 512-token
prompt budget. Long native recipes, caller system instructions, streaming, tools,
media and exact public token preflight are unsupported. General AI quality,
completed live ChatGPT generation, physical customer-menu behavior, customer
browser download delivery, customer-device acceptance and other platforms are
not qualified. Unqualified targets: {", ".join(legacy.UNQUALIFIED)}.

Packages are unsigned and not notarised. Follow your organisation's policy;
never disable OS protections. Work and backups are local and unencrypted.
Sinter remains one trusted user's open workbench; no autonomous communications,
grant submission or hosted multiuser service is included.
"""


def _external_executable_digests(read_role):
    digests = set()
    for version in ("0.5.3", "0.5.4rc1", "0.5.4rc2", "0.5.4rc3"):
        row = strict_json(read_role("replacement", version + "/outer.json"))
        host = row.get("host")
        require(
            type(host) is dict and type(host.get("before")) is dict,
            "Original external host observation object is missing.",
        )
        tools = host["before"].get("tools")
        require(
            type(tools) is dict
            and set(tools) == {"docker", "chromium", "python", "playwright_node"},
            "Original external executable fingerprint roles are incomplete.",
        )
        for item in tools.values():
            value = item.get("sha256") if type(item) is dict else None
            require(
                type(value) is str and re.fullmatch(r"[0-9a-f]{64}", value),
                "External executable fingerprint lacks an exact digest.",
            )
            digests.add(value)
    return digests


def _catalog(context, pins, snapshots, verification):
    forbidden = _external_executable_digests(
        lambda scope, name: regular(context.roots()[scope] / name)
    )
    require(
        not forbidden.intersection(
            row["sha256"]
            for snapshot in snapshots.values()
            for row in snapshot["files"].values()
        ),
        "External host executable bytes must not be exported as qualification evidence.",
    )
    identities = [
        {"name": "final-source", "kind": "git-commit", "value": pins.source_commit},
        {"name": "installer", "kind": "sha256", "value": pins.installer_sha256},
        {"name": "native-binary", "kind": "sha256", "value": pins.native_binary_sha256},
    ]
    labels, roles, blobs = [], [], {}
    for scope, root in context.roots().items():
        for name, row in snapshots[scope]["files"].items():
            raw = regular(root / name)
            require(record(raw) == row, "Original bytes changed before finite export.")
            identity = (
                "installer"
                if scope == "candidate" and name == product_names()[0]
                else "native-binary"
                if scope == "candidate" and name == product_names()[1]
                else "final-source"
            )
            labels.append(
                {
                    "scope": scope,
                    "name": name,
                    "namespace": "host",
                    "value": str(root / name),
                }
            )
            roles.append(
                {
                    "scope": scope,
                    "role": name,
                    "identity": identity,
                    "label": name,
                    **row,
                }
            )
            blobs[row["sha256"]] = raw
        raw = canonical(snapshots[scope])
        name = "original-closed-inventory.json"
        require(
            name not in snapshots[scope]["files"],
            "Original tree conflicts with its exact inventory role.",
        )
        labels.append(
            {"scope": scope, "name": name, "namespace": "host", "value": str(root)}
        )
        roles.append(
            {
                "scope": scope,
                "role": name,
                "identity": "final-source",
                "label": name,
                **record(raw),
            }
        )
        blobs[sha(raw)] = raw
    raw = canonical(verification)
    labels.append(
        {
            "scope": "original-authorization",
            "name": "semantic-revalidation.json",
            "namespace": "host",
            "value": "original-tree verification output; not public replay authority",
        }
    )
    roles.append(
        {
            "scope": "original-authorization",
            "role": "semantic-revalidation.json",
            "identity": "final-source",
            "label": "semantic-revalidation.json",
            **record(raw),
        }
    )
    blobs[sha(raw)] = raw
    authority = {
        "schema": transport.AUTHORITY_SCHEMA,
        "identities": identities,
        "labels": labels,
        "roles": roles,
        "directories": ["blobs"],
    }
    transport.validate_authority(canonical(authority))
    index = {**authority, "schema": transport.INDEX_SCHEMA}
    raw_index = canonical(index)
    require(
        len(raw_index) + sum(map(len, blobs.values())) <= MAX_BUNDLE,
        "Complete finite qualification export exceeds the unchanged bundle bound.",
    )
    return authority, raw_index, blobs


def _write_checksums(stage):
    names = sorted(
        path.name
        for path in stage.iterdir()
        if path.is_file() and path.name != "SHA256SUMS.txt"
    )
    (stage / "SHA256SUMS.txt").write_text(
        "".join(f"{sha(_asset_bytes(stage / name))}  {name}\n" for name in names),
        encoding="ascii",
    )


@contextmanager
def _writing_bundle(path):
    bundle = zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED)
    primary = None
    try:
        yield bundle
    except BaseException as error:
        primary = error
        raise
    finally:
        try:
            bundle.close()
        except BaseException as error:
            if primary is None:
                raise
            primary.rc4_secondary_errors = (
                *getattr(primary, "rc4_secondary_errors", ()),
                error,
            )


def prepare_original(context, output, pins):
    """Create one new eight-asset stage only after original semantic qualification."""
    output = Path(output)
    require(not output.exists(), "A candidate stage is never overwritten.")
    for root in context.roots().values():
        require(
            not output.resolve().is_relative_to(root.resolve()),
            "Staging must be outside every original evidence tree.",
        )
    snapshots = _inventories(context)
    verification = verify_original(context, pins)
    require(
        _inventories(context) == snapshots,
        "Original raw inventories changed during qualification.",
    )
    authority, index, blobs = _catalog(context, pins, snapshots, verification)
    output.parent.mkdir(parents=True, exist_ok=True)
    stage = Path(tempfile.mkdtemp(prefix="rc4-stage-", dir=output.parent))
    try:
        for name in product_names():
            shutil.copyfile(context.candidate / name, stage / name)
        with _writing_bundle(stage / f"sinter-{VERSION}-qualification.zip") as bundle:
            bundle.writestr("catalog.json", index)
            for digest, raw in sorted(blobs.items()):
                bundle.writestr("blobs/" + digest, raw)
        (stage / "RELEASE-NOTES.md").write_text(
            release_notes(
                pins.source_commit,
                operations_catalogue=verification["gates"]["workflow"][
                    "operations_catalogue"
                ],
            ),
            encoding="utf-8",
        )
        assets = [
            {"path": path.name, **record(_asset_bytes(path))}
            for path in sorted(stage.iterdir())
        ]
        manifest = {
            "schema": SCHEMA,
            "version": VERSION,
            "source_commit": pins.source_commit,
            "repository": legacy.REPOSITORY,
            "tag": "v" + VERSION,
            "prerelease": True,
            "latest": False,
            "qualified_targets": [legacy.TARGET],
            "unqualified_targets": legacy.UNQUALIFIED,
            "all_platform_release_qualified": False,
            "publication_executed": False,
            "original_authorization_required": True,
            "historical_semantic_replay": False,
            "new_installed_execution": False,
            "trusted_pins": asdict(pins),
            "catalog_index_sha256": sha(index),
            "catalog_authority": authority,
            "original_semantic_result": verification,
            "assets": assets,
        }
        path = stage / "candidate-release-manifest.json"
        path.write_bytes(canonical(manifest))
        _write_checksums(stage)
        inspect_public(path, manifest_sha256=sha(regular(path)), pins=pins)
        require(
            _inventories(context) == snapshots,
            "Original evidence changed while exporting the finite stage.",
        )
        stage.rename(output)
    except BaseException as error:
        # Keep every unpublished byte from a failed stage. An automatic cleanup
        # must not overwrite the first failure or erase its diagnostic artifacts.
        try:
            error.rc4_unpublished_stage = str(stage)
        except Exception:
            pass
        raise
    return output / "candidate-release-manifest.json"


def _zip_members(bundle):
    rows, total = {}, 0
    for row in bundle.infolist():
        name = legacy._safe_name(row.filename)
        mode = stat.S_IFMT(row.external_attr >> 16)
        require(
            name not in rows
            and not row.is_dir()
            and mode in {0, stat.S_IFREG}
            and not row.external_attr & 0x10,
            "Qualification export contains a duplicate, directory, redirect or special member.",
        )
        total += row.file_size
        require(
            0 <= row.file_size <= MAX_FILE and total <= MAX_BUNDLE,
            "Qualification export exceeds the unchanged expanded bounds.",
        )
        rows[name] = row
    return rows


def _public_source(stage, pins):
    # Only bounded data parsing. No source code is imported or executed.
    with zipfile.ZipFile(io.BytesIO(regular(stage / product_names()[2]))) as bundle:
        require(
            bundle.comment == pins.source_commit.encode("ascii"),
            "Source ZIP origin differs from the independent final commit.",
        )
        rows, files, total = {}, {}, 0
        for row in bundle.infolist():
            name = legacy._safe_name(
                row.filename.rstrip("/") if row.is_dir() else row.filename
            )
            require(name not in rows, "Source ZIP member repeats.")
            rows[name] = row
            total += row.file_size
            require(
                row.file_size <= MAX_FILE
                and total <= MAX_BUNDLE
                and stat.S_IFMT(row.external_attr >> 16)
                in {0, stat.S_IFDIR, stat.S_IFREG},
                "Source ZIP member type or expanded size differs.",
            )
            if not row.is_dir():
                files[name] = bundle.read(row)
    match = re.findall(
        rb'^__version__ = ["\']([^"\']+)["\']$',
        files.get("src/sinter/__init__.py", b""),
        re.M,
    )
    require(
        match == [VERSION.encode("ascii")],
        "Exported source is not the final RC4 version; DEV cannot qualify.",
    )
    require(
        tool_manifest(files) == pins.tool_manifest_sha256
        and all(name in files for name in REQUIRED_TOOLS),
        "Public final tool/source identity differs.",
    )
    with zipfile.ZipFile(io.BytesIO(regular(stage / product_names()[3]))) as bundle:
        rows = _zip_members(bundle)
        expected = {
            name.removeprefix("src/")
            for name in files
            if name.startswith("src/sinter/")
        } | {"LICENSE", "NOTICE", "__main__.py"}
        require(
            set(rows) == expected, "Portable app inventory differs from final source."
        )
        for name in expected - {"__main__.py"}:
            require(
                bundle.read(rows[name])
                == files["src/" + name if name.startswith("sinter/") else name],
                "Portable app differs from the pinned source bytes.",
            )
        require(
            bundle.read(rows["__main__.py"])
            == b"# -*- coding: utf-8 -*-\nimport sinter.cli\nsinter.cli.launch()\n",
            "Portable entry point differs.",
        )
    with tarfile.open(
        fileobj=io.BytesIO(regular(stage / product_names()[1]))
    ) as bundle:
        members = legacy._runtime_members(bundle, "Sinter/", strict_root=True)
    require(
        members.get("Sinter", ())[:2] == ("file", pins.native_binary_sha256),
        "Exported native archive binary differs from the independently pinned installed binary.",
    )
    return files


def inspect_public(manifest_path, *, manifest_sha256, pins):
    """Inspect externally pinned finite bytes only; never authorise a release tag.

    Original labels remain opaque. This operation does not open original trees,
    execute commands, import exported code or create files.
    """
    require(type(pins) is OriginalPins, "Independent product/source pins are required.")
    pins.validate()
    path = Path(manifest_path)
    require(
        path.name == "candidate-release-manifest.json",
        "Use the exact staged manifest filename.",
    )
    raw = regular(path)
    require(
        type(manifest_sha256) is str
        and re.fullmatch(r"[0-9a-f]{64}", manifest_sha256)
        and sha(raw) == manifest_sha256,
        "The staged manifest differs from its independent external pin.",
    )
    manifest = strict_json(raw)
    required = {
        "schema": SCHEMA,
        "version": VERSION,
        "source_commit": pins.source_commit,
        "repository": legacy.REPOSITORY,
        "tag": "v" + VERSION,
        "prerelease": True,
        "latest": False,
        "qualified_targets": [legacy.TARGET],
        "unqualified_targets": legacy.UNQUALIFIED,
        "all_platform_release_qualified": False,
        "publication_executed": False,
        "original_authorization_required": True,
        "historical_semantic_replay": False,
        "new_installed_execution": False,
        "trusted_pins": asdict(pins),
    }
    require(
        set(manifest)
        == set(required)
        | {
            "catalog_index_sha256",
            "catalog_authority",
            "original_semantic_result",
            "assets",
        }
        and all(
            type(manifest.get(key)) is type(value) and manifest[key] == value
            for key, value in required.items()
        ),
        "Public manifest identity, exact fields or narrower claims differ.",
    )
    stage = path.parent
    inventory = _inventory(stage, encoded_stage=True)
    asset_names = {
        *product_names(),
        f"sinter-{VERSION}-qualification.zip",
        "RELEASE-NOTES.md",
    }
    require(
        set(inventory["files"]) == asset_names | {path.name, "SHA256SUMS.txt"}
        and inventory["directories"] == [],
        "Require the exact eight staged release assets, without extra files or directories.",
    )
    assets = manifest["assets"]
    require(
        type(assets) is list
        and all(
            type(row) is dict and set(row) == {"path", "bytes", "sha256"}
            for row in assets
        ),
        "Asset rows differ.",
    )
    require(
        len(assets) == len(asset_names)
        and {row["path"] for row in assets} == asset_names,
        "Asset names omit or duplicate a published role.",
    )
    for row in assets:
        require(
            type(row["bytes"]) is int
            and type(row["sha256"]) is str
            and {"bytes": row["bytes"], "sha256": row["sha256"]}
            == inventory["files"][row["path"]],
            "Actual staged asset bytes differ from the externally pinned manifest.",
        )
    sums = legacy._checksum_entries(stage / "SHA256SUMS.txt")
    require(
        sums
        == {
            name: row["sha256"]
            for name, row in inventory["files"].items()
            if name != "SHA256SUMS.txt"
        },
        "Checksums do not cover exact staged bytes.",
    )
    for name, digest in zip(
        product_names(),
        (
            pins.installer_sha256,
            pins.native_archive_sha256,
            pins.source_archive_sha256,
            pins.portable_sha256,
        ),
    ):
        require(
            inventory["files"][name]["sha256"] == digest,
            "An exported product differs from its independent final pin.",
        )
    authority_raw = canonical(manifest["catalog_authority"])
    authority = transport.validate_authority(authority_raw)
    require(
        authority.identities
        == {
            "final-source": ("git-commit", pins.source_commit),
            "installer": ("sha256", pins.installer_sha256),
            "native-binary": ("sha256", pins.native_binary_sha256),
        },
        "Finite evidence identities differ from the independent final product pins.",
    )
    with zipfile.ZipFile(
        io.BytesIO(_asset_bytes(stage / f"sinter-{VERSION}-qualification.zip"))
    ) as bundle:
        rows = _zip_members(bundle)
        require(
            set(rows)
            == {"catalog.json", *("blobs/" + digest for digest in authority.blobs)},
            "Finite qualification ZIP inventory is missing or unexpected.",
        )
        index = bundle.read(rows["catalog.json"])
        require(
            sha(index) == manifest["catalog_index_sha256"]
            and transport.validate_authority(index, schema=transport.INDEX_SCHEMA)
            == authority,
            "Exact exported index differs from its pinned authority.",
        )
        for digest, size in authority.blobs.items():
            raw_blob = bundle.read(rows["blobs/" + digest])
            require(
                len(raw_blob) == size and sha(raw_blob) == digest,
                "A complete finite raw blob differs.",
            )

        def role(scope, name):
            require(
                (scope, name) in authority.roles,
                "A required raw qualification role is missing.",
            )
            selected = authority.roles[(scope, name)]
            return bundle.read(rows[selected.blob])

        require(
            not _external_executable_digests(role).intersection(authority.blobs),
            "Public qualification includes forbidden external host executable bytes.",
        )
        for name in product_names():
            require(
                role("candidate", name) == regular(stage / name),
                "An uploaded product differs from its actual retained qualification bytes.",
            )
        require(
            sha(role("candidate", f"Sinter-{VERSION}-linux-x64-test.json"))
            == pins.package_receipt_sha256
            and sha(role("independent-review", "final-artifact-review.json"))
            == pins.independent_review_sha256,
            "Actual product receipt or independent review differs from its external pin.",
        )
        require(
            strict_json(role("original-authorization", "semantic-revalidation.json"))
            == manifest["original_semantic_result"],
            "Original semantic output changed; it remains historical data, never public admission authority.",
        )
        for scope in SCOPES:
            strict_json(role(scope, "original-closed-inventory.json"))
    source = _public_source(stage, pins)
    from tools.installed_workflow_qualification import source_operations

    require(
        regular(stage / "RELEASE-NOTES.md")
        == release_notes(
            pins.source_commit, operations_catalogue=len(source_operations(source))
        ).encode("utf-8"),
        "Public release notes differ from the deliberately bounded source catalogue policy.",
    )
    require(
        _inventory(stage, encoded_stage=True) == inventory,
        "The exact staged directory changed during public byte inspection.",
    )
    return {
        "schema": PUBLIC_SCHEMA,
        "version": VERSION,
        "source_commit": pins.source_commit,
        "manifest_sha256": manifest_sha256,
        "exported_byte_integrity_verified": True,
        "product_identity_verified": True,
        "historical_semantic_replay": False,
        "new_installed_execution": False,
        "release_authorized": False,
        "original_environment_required_for_authorization": True,
        "assets": assets,
    }


def authorize_original(manifest_path, *, context, pins, manifest_sha256):
    """Immediately rerun public exact-byte checks and original semantic gates.

    Neither a successful public inspection nor saved admission booleans reach
    this operation without every original raw tree and explicit independent pins.
    """
    inspect_public(manifest_path, manifest_sha256=manifest_sha256, pins=pins)
    result = verify_original(context, pins)
    manifest = strict_json(regular(manifest_path))
    require(
        result == manifest["original_semantic_result"],
        "Fresh original semantic result differs from the sealed stage.",
    )
    authority, index, _blobs = _catalog(context, pins, _inventories(context), result)
    require(
        canonical(authority) == canonical(manifest["catalog_authority"])
        and sha(index) == manifest["catalog_index_sha256"],
        "Actual original raw inventories differ from the complete exported final stage.",
    )
    inspect_public(manifest_path, manifest_sha256=manifest_sha256, pins=pins)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="operation", required=True)
    for operation in ("prepare-original", "inspect-public", "authorize-original"):
        command = commands.add_parser(operation)
        command.add_argument("--trusted-pins", type=Path, required=True)
        command.add_argument("--trusted-pins-sha256", required=True)
        if operation != "inspect-public":
            command.add_argument("--original-context", type=Path, required=True)
            command.add_argument("--original-context-sha256", required=True)
        if operation == "prepare-original":
            command.add_argument("--output", type=Path, required=True)
        else:
            command.add_argument("--manifest", type=Path, required=True)
            command.add_argument("--manifest-sha256", required=True)
    args = parser.parse_args(argv)
    try:
        pins = _load_external(
            args.trusted_pins, args.trusted_pins_sha256, PINS_SCHEMA, OriginalPins
        )
        if args.operation == "inspect-public":
            result = inspect_public(
                args.manifest, manifest_sha256=args.manifest_sha256, pins=pins
            )
        else:
            context = _load_external(
                args.original_context,
                args.original_context_sha256,
                CONTEXT_SCHEMA,
                OriginalContext,
            )
            if args.operation == "prepare-original":
                path = prepare_original(context, args.output, pins)
                result = {
                    "manifest": str(path),
                    "manifest_sha256": sha(regular(path)),
                    "publication_executed": False,
                }
            else:
                result = authorize_original(
                    args.manifest,
                    context=context,
                    pins=pins,
                    manifest_sha256=args.manifest_sha256,
                )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        ImportError,
        zipfile.BadZipFile,
        tarfile.TarError,
    ) as error:
        parser.exit(1, f"{parser.prog}: RC4 original qualification refused: {error}\n")
    print(json.dumps(result, sort_keys=True, ensure_ascii=True, allow_nan=False))


if __name__ == "__main__":
    main()
