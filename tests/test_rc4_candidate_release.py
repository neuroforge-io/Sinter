"""Source-only orchestration/integrity controls; no installed RC4 proof is made."""

from __future__ import annotations

import ast
import copy
import io
import os
import shutil
import subprocess
import sys
import tarfile
import types
import zipfile
from dataclasses import asdict, replace
from pathlib import Path

import pytest

from tools import candidate_qualification as legacy
from tools import candidate_release as dispatch
from tools import rc4_candidate_release as release
from tools import release_tag
from tools.installed_workflow_qualification import source_operations

COMMIT = "a" * 40


def raw_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(release.canonical(value))


def catalogue_alignment_runtime(count=None):
    """Actual source catalogue or its exact legacy profile without funding."""
    raw = (release.ROOT / "src/sinter/runtime.py").read_bytes()
    if count is None or count == 54:
        return raw
    assert count == 53
    tree = ast.parse(raw)
    entries = next(
        node.value
        for node in tree.body
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == "_OPERATIONS"
            for target in node.targets
        )
    )
    entries.elts = [
        entry
        for entry in entries.elts
        if entry.args[0].value != "campaigns.funding_summary"
    ]
    return ast.unparse(tree).encode()


def sample(tmp_path, monkeypatch, *, catalogue_count=None):
    if not release.transport.physical_reader_supported():
        pytest.skip(
            "Actual finite payload inspection requires the reviewed POSIX no-follow reader; this host is not qualified."
        )
    roots = {}
    for scope in release.SCOPES:
        root = tmp_path / ("original-" + scope)
        root.mkdir()
        (root / "empty-directory").mkdir()
        (root / "retained.txt").write_bytes(
            b"Fictional original evidence: e\xcc\x81 \xf0\x9f\x90\x9d\n"
        )
        roots[scope.replace("-", "_")] = root
    for name in ("repository", "replacement_repository", "replacement_owned_root"):
        roots[name] = tmp_path / name
        roots[name].mkdir()
    roots["chromium"] = tmp_path / "EXTERNAL-browser-not-opened"
    context = release.OriginalContext(**roots)
    files = {
        name: b"# Synthetic test-only gate content.\n"
        for name in release.REQUIRED_TOOLS
    }
    files.update(
        {
            "src/sinter/__init__.py": b'__version__ = "0.5.4rc4"\n',
            "src/sinter/demo.py": b"# Fictional local source\n",
            "src/sinter/runtime.py": catalogue_alignment_runtime(catalogue_count),
            "LICENSE": b"Synthetic licence control\n",
            "NOTICE": b"Synthetic notice control\n",
        }
    )
    products = release.product_names()
    archive = io.BytesIO()
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.comment = COMMIT.encode("ascii")
        for name, data in files.items():
            bundle.writestr(name, data)
    (context.candidate / products[2]).write_bytes(archive.getvalue())
    portable = io.BytesIO()
    with zipfile.ZipFile(portable, "w") as bundle:
        for name, data in files.items():
            if name.startswith("src/sinter/"):
                bundle.writestr(name.removeprefix("src/"), data)
        for name in ("LICENSE", "NOTICE"):
            bundle.writestr(name, files[name])
        bundle.writestr(
            "__main__.py",
            b"# -*- coding: utf-8 -*-\nimport sinter.cli\nsinter.cli.launch()\n",
        )
    (context.candidate / products[3]).write_bytes(portable.getvalue())
    binary = b"SYNTHETIC TEST-ONLY NATIVE BINARY; NOT AN INSTALLER\n"
    native = io.BytesIO()
    with tarfile.open(fileobj=native, mode="w:gz") as bundle:
        item = tarfile.TarInfo("Sinter/Sinter")
        item.size = len(binary)
        item.mode = 0o755
        bundle.addfile(item, io.BytesIO(binary))
    (context.candidate / products[1]).write_bytes(native.getvalue())
    (context.candidate / products[0]).write_bytes(
        b"SYNTHETIC TEST-ONLY DEB PIN; NOT A DEBIAN PACKAGE\n"
    )
    receipt_name = f"Sinter-{release.VERSION}-linux-x64-test.json"
    raw_json(context.candidate / receipt_name, {"source_only_synthetic_fixture": True})
    review = {"source_only_synthetic_fixture": True, "not_a_clean_install": True}
    raw_json(context.independent_review / "final-artifact-review.json", review)
    for name in release.legacy.REVIEW_FILES[1:]:
        (context.independent_review / name).write_bytes(
            b"Synthetic raw test bytes; no installed proof.\n"
        )
    tools = {
        name: {"sha256": str(index + 1) * 64}
        for index, name in enumerate(
            ("docker", "chromium", "python", "playwright_node")
        )
    }
    for version in ("0.5.3", "0.5.4rc1", "0.5.4rc2", "0.5.4rc3"):
        raw_json(
            context.replacement / version / "outer.json",
            {
                "schema": "sinter-rc4-replacement-owner/v2",
                "host": {"before": {"tools": tools}},
            },
        )
    raw_json(
        context.native / "handoff-container/browser.json",
        {"schema": "sinter-rc4-native-handoff-browser/v3"},
    )
    for name in products[:1] + (receipt_name,):
        shutil.copyfile(context.candidate / name, context.replacement_candidate / name)
    pins = release.OriginalPins(
        source_commit=COMMIT,
        source_archive_sha256=release.sha(archive.getvalue()),
        tool_manifest_sha256=release.tool_manifest(files),
        installer_sha256=release.sha(release.regular(context.candidate / products[0])),
        package_receipt_sha256=release.sha(
            release.regular(context.candidate / receipt_name)
        ),
        native_archive_sha256=release.sha(native.getvalue()),
        portable_sha256=release.sha(portable.getvalue()),
        native_binary_sha256=release.sha(binary),
        independent_review_sha256=release.sha(
            release.regular(context.independent_review / "final-artifact-review.json")
        ),
        chromium_sha256="5" * 64,
        image_id="sha256:" + "6" * 64,
    )
    synthetic_result = {
        "schema": release.AUTHORIZATION_SCHEMA,
        "source_only_synthetic_orchestration": True,
        "not_installed_qualification": True,
        "gates": {"workflow": {"operations_catalogue": len(source_operations(files))}},
    }
    monkeypatch.setattr(
        release,
        "verify_original",
        lambda supplied_context, supplied_pins: copy.deepcopy(synthetic_result),
    )
    return context, pins, synthetic_result, files


def stage_fixture(tmp_path, monkeypatch, *, catalogue_count=None):
    context, pins, result, files = sample(
        tmp_path, monkeypatch, catalogue_count=catalogue_count
    )
    manifest = release.prepare_original(context, tmp_path / "stage", pins)
    return (
        context,
        pins,
        result,
        files,
        manifest,
        release.sha(release.regular(manifest)),
    )


def reseal_stage(path, mutate):
    value = release.strict_json(release.regular(path))
    mutate(value)
    path.write_bytes(release.canonical(value))
    release._write_checksums(path.parent)
    return release.sha(release.regular(path))


def test_public_positive_is_only_integrity_and_has_eight_assets(tmp_path, monkeypatch):
    _context, pins, _result, _files, manifest, digest = stage_fixture(
        tmp_path, monkeypatch
    )
    observed = release.inspect_public(manifest, manifest_sha256=digest, pins=pins)
    assert len(list(manifest.parent.iterdir())) == 8
    assert observed["exported_byte_integrity_verified"] is True
    assert observed["historical_semantic_replay"] is False
    assert observed["new_installed_execution"] is False
    assert observed["release_authorized"] is False


def test_public_reads_only_relocated_stage_without_original_labels(
    tmp_path, monkeypatch
):
    context, pins, _result, _files, manifest, digest = stage_fixture(
        tmp_path, monkeypatch
    )
    target = tmp_path / "another-root" / "stage"
    target.parent.mkdir()
    shutil.copytree(manifest.parent, target)
    for root in context.roots().values():
        shutil.rmtree(root)
    forbidden = []
    original_tree = release.transport._Tree.__init__

    def guarded_tree(tree, root):
        selected = Path(root).absolute()
        if not selected.is_relative_to(target.absolute()):
            forbidden.append(str(selected))
            raise AssertionError("Original or external label was opened.")
        return original_tree(tree, root)

    monkeypatch.setattr(release.transport._Tree, "__init__", guarded_tree)
    monkeypatch.setattr(
        subprocess, "run", lambda *a, **k: pytest.fail("Public process execution")
    )
    monkeypatch.setattr(
        subprocess, "Popen", lambda *a, **k: pytest.fail("Public process launch")
    )
    monkeypatch.setattr(
        release,
        "verify_original",
        lambda *a, **k: pytest.fail("Public semantic invocation"),
    )
    result = release.inspect_public(
        target / manifest.name, manifest_sha256=digest, pins=pins
    )
    assert result["release_authorized"] is False
    assert forbidden == []


@pytest.mark.parametrize("field", list(release.OriginalPins.__dataclass_fields__))
def test_changed_independent_product_or_source_pin_refuses(
    tmp_path, monkeypatch, field
):
    _context, pins, _result, _files, manifest, digest = stage_fixture(
        tmp_path, monkeypatch
    )
    value = (
        "b" * 40
        if field == "source_commit"
        else "sha256:" + "b" * 64
        if field == "image_id"
        else "b" * 64
    )
    with pytest.raises(ValueError):
        release.inspect_public(
            manifest, manifest_sha256=digest, pins=replace(pins, **{field: value})
        )


@pytest.mark.parametrize(
    "field",
    [
        "historical_semantic_replay",
        "new_installed_execution",
        "all_platform_release_qualified",
        "latest",
        "publication_executed",
    ],
)
def test_resealed_public_claim_escalation_refuses(tmp_path, monkeypatch, field):
    _context, pins, _result, _files, manifest, _digest = stage_fixture(
        tmp_path, monkeypatch
    )
    digest = reseal_stage(manifest, lambda value: value.update({field: True}))
    with pytest.raises(ValueError, match="narrower claims"):
        release.inspect_public(manifest, manifest_sha256=digest, pins=pins)


@pytest.mark.parametrize(
    "change",
    [
        "extra-file",
        "extra-directory",
        "missing",
        "changed",
        "wrong-manifest-pin",
        "bool-size",
        "extra-manifest-key",
        "duplicate-assets",
        "missing-raw-review",
    ],
)
def test_closed_public_stage_and_raw_roles_refuse(tmp_path, monkeypatch, change):
    _context, pins, _result, _files, manifest, digest = stage_fixture(
        tmp_path, monkeypatch
    )
    if change == "extra-file":
        (manifest.parent / "unapproved.txt").write_bytes(b"new")
    elif change == "extra-directory":
        (manifest.parent / "unexpected-empty").mkdir()
    elif change == "missing":
        (manifest.parent / release.product_names()[0]).unlink()
    elif change == "changed":
        (manifest.parent / release.product_names()[0]).write_bytes(b"changed")
    elif change == "wrong-manifest-pin":
        digest = "e" * 64
    elif change == "bool-size":
        digest = reseal_stage(
            manifest, lambda value: value["assets"][0].update({"bytes": True})
        )
    elif change == "extra-manifest-key":
        digest = reseal_stage(
            manifest, lambda value: value.update({"release_authorized": True})
        )
    elif change == "duplicate-assets":
        digest = reseal_stage(
            manifest, lambda value: value["assets"].__setitem__(0, value["assets"][1])
        )
    elif change == "missing-raw-review":
        digest = reseal_stage(
            manifest,
            lambda value: value["catalog_authority"]["roles"].__setitem__(
                0, {**value["catalog_authority"]["roles"][0], "role": "other-role"}
            ),
        )
    with pytest.raises((ValueError, OSError)):
        release.inspect_public(manifest, manifest_sha256=digest, pins=pins)


@pytest.mark.parametrize("member", ["../escape", "blobs/unknown", "catalog.json"])
def test_duplicate_or_unknown_qualification_members_refuse(
    tmp_path, monkeypatch, member
):
    _context, pins, _result, _files, manifest, _digest = stage_fixture(
        tmp_path, monkeypatch
    )
    qualification = manifest.parent / f"sinter-{release.VERSION}-qualification.zip"
    with zipfile.ZipFile(qualification, "a") as archive:
        if member == "catalog.json":
            with pytest.warns(UserWarning, match="Duplicate name"):
                archive.writestr(member, b"unapproved")
        else:
            archive.writestr(member, b"unapproved")

    def edit(value):
        for row in value["assets"]:
            if row["path"] == qualification.name:
                row.update(release.record(release.regular(qualification)))

    digest = reseal_stage(manifest, edit)
    with pytest.raises(ValueError):
        release.inspect_public(manifest, manifest_sha256=digest, pins=pins)


@pytest.mark.parametrize("scope", release.SCOPES)
def test_original_gate_requires_each_actual_tree(tmp_path, monkeypatch, scope):
    context, pins, _result, _files = sample(tmp_path, monkeypatch)
    shutil.rmtree(context.roots()[scope])
    monkeypatch.undo()
    with pytest.raises((ValueError, OSError)):
        release.verify_original(context, pins)


def test_public_integrity_never_substitutes_for_actual_original_gate(
    tmp_path, monkeypatch
):
    context, pins, _result, _files, manifest, digest = stage_fixture(
        tmp_path, monkeypatch
    )
    called = []

    def refuse(_context, _pins):
        called.append("original")
        raise ValueError("Actual original gate refused")

    monkeypatch.setattr(release, "verify_original", refuse)
    assert (
        release.inspect_public(manifest, manifest_sha256=digest, pins=pins)[
            "release_authorized"
        ]
        is False
    )
    with pytest.raises(ValueError, match="Actual original"):
        release.authorize_original(
            manifest, context=context, pins=pins, manifest_sha256=digest
        )
    assert called == ["original"]


def test_original_authorization_rechecks_bytes_after_gate(tmp_path, monkeypatch):
    context, pins, result, _files, manifest, digest = stage_fixture(
        tmp_path, monkeypatch
    )

    def gate(_context, _pins):
        (manifest.parent / "RELEASE-NOTES.md").write_bytes(
            b"modified during original verification"
        )
        return result

    monkeypatch.setattr(release, "verify_original", gate)
    with pytest.raises(ValueError, match="asset bytes differ"):
        release.authorize_original(
            manifest, context=context, pins=pins, manifest_sha256=digest
        )


def test_original_authorization_rechecks_exact_original_raw_inventory(
    tmp_path, monkeypatch
):
    context, pins, result, _files, manifest, digest = stage_fixture(
        tmp_path, monkeypatch
    )
    (context.workflow / "retained.txt").write_bytes(b"changed actual raw evidence")
    with pytest.raises(ValueError, match="original raw inventories differ"):
        release.authorize_original(
            manifest, context=context, pins=pins, manifest_sha256=digest
        )


def test_prepare_refuses_original_failure_before_output(tmp_path, monkeypatch):
    context, pins, _result, _files = sample(tmp_path, monkeypatch)

    def refuse(_context, _pins):
        raise ValueError("First actual raw semantic gate refused")

    monkeypatch.setattr(release, "verify_original", refuse)
    output = tmp_path / "stage"
    with pytest.raises(ValueError, match="First actual"):
        release.prepare_original(context, output, pins)
    assert not output.exists()


def test_prepare_does_not_replace_existing_stage(tmp_path, monkeypatch):
    context, pins, _result, _files, manifest, _digest = stage_fixture(
        tmp_path, monkeypatch
    )
    raw = manifest.read_bytes()
    with pytest.raises(ValueError, match="never overwritten"):
        release.prepare_original(context, manifest.parent, pins)
    assert manifest.read_bytes() == raw


def test_legacy_rc4_policy_still_refuses_but_exact_new_dispatch_runs_original_gate(
    tmp_path, monkeypatch
):
    with pytest.raises(ValueError, match="no explicit qualification"):
        legacy._identity(release.VERSION, COMMIT)
    context, pins, _result, _files, manifest, digest = stage_fixture(
        tmp_path, monkeypatch
    )
    observed = []

    def original(path, **kwargs):
        observed.append((path, kwargs))
        return {"version": release.VERSION}

    monkeypatch.setattr(release, "authorize_original", original)
    result = dispatch.verify_plan(
        manifest, rc4_context=context, rc4_pins=pins, rc4_manifest_sha256=digest
    )
    assert result == {"version": release.VERSION}
    assert observed == [
        (manifest, {"context": context, "pins": pins, "manifest_sha256": digest})
    ]


def test_exact_dispatch_without_original_pins_cannot_accept_public_success(
    tmp_path, monkeypatch
):
    _context, _pins, _result, _files, manifest, _digest = stage_fixture(
        tmp_path, monkeypatch
    )
    monkeypatch.undo()
    with pytest.raises(ValueError, match="Independent product/source pins"):
        dispatch.verify_plan(manifest)


def test_tag_refuses_before_network_without_complete_original_authorization(
    tmp_path, monkeypatch
):
    _context, _pins, _result, _files, manifest, _digest = stage_fixture(
        tmp_path, monkeypatch
    )
    monkeypatch.setattr(
        release_tag,
        "_api",
        lambda *a, **k: pytest.fail("Network attempted before original qualification"),
    )
    with pytest.raises(ValueError, match="RC4 tags require"):
        release_tag.ensure_release_tag(
            "neuroforge-io/Sinter", "v0.5.4rc4", COMMIT, manifest
        )


def test_tag_rechecks_original_gate_immediately_before_only_post(tmp_path, monkeypatch):
    _context, _pins, _result, _files, manifest, _digest = stage_fixture(
        tmp_path, monkeypatch
    )
    events = []

    def identity(*args, **kwargs):
        events.append("original-authorization")

    def api(repository, method, endpoint, payload=None):
        events.append(method)
        return (
            (404, {})
            if method == "GET"
            else (
                201,
                {
                    "ref": "refs/tags/v0.5.4rc4",
                    "object": {"type": "commit", "sha": COMMIT},
                },
            )
        )

    monkeypatch.setattr(release_tag, "_candidate_identity", identity)
    monkeypatch.setattr(release_tag, "_api", api)
    release_tag.ensure_release_tag(
        "neuroforge-io/Sinter", "v0.5.4rc4", COMMIT, manifest
    )
    assert events == ["original-authorization", "GET", "original-authorization", "POST"]


def test_tag_no_post_when_final_original_recheck_refuses(tmp_path, monkeypatch):
    _context, _pins, _result, _files, manifest, _digest = stage_fixture(
        tmp_path, monkeypatch
    )
    events = []

    def identity(*args, **kwargs):
        events.append("original-authorization")
        if len(events) > 1:
            raise ValueError("Original changed before tag")

    def api(repository, method, endpoint, payload=None):
        events.append(method)
        assert method == "GET"
        return 404, {}

    monkeypatch.setattr(release_tag, "_candidate_identity", identity)
    monkeypatch.setattr(release_tag, "_api", api)
    with pytest.raises(ValueError, match="changed before tag"):
        release_tag.ensure_release_tag(
            "neuroforge-io/Sinter", "v0.5.4rc4", COMMIT, manifest
        )
    assert events == ["original-authorization", "GET", "original-authorization"]


@pytest.mark.parametrize("field", ["context", "pins"])
def test_external_authorization_files_require_independent_hashes(
    tmp_path, monkeypatch, field
):
    context, pins, _result, _files = sample(tmp_path, monkeypatch)
    context_file, pins_file = tmp_path / "context.json", tmp_path / "pins.json"
    raw_json(
        context_file,
        {
            "schema": release.CONTEXT_SCHEMA,
            **{name: str(value) for name, value in asdict(context).items()},
        },
    )
    raw_json(pins_file, {"schema": release.PINS_SCHEMA, **asdict(pins)})
    hashes = [
        release.sha(release.regular(context_file)),
        release.sha(release.regular(pins_file)),
    ]
    hashes[0 if field == "context" else 1] = "f" * 64
    with pytest.raises(ValueError, match="explicit pin"):
        release.load_original(context_file, hashes[0], pins_file, hashes[1])


def test_source_DEV_and_missing_final_tools_refuse_without_optional_dependencies(
    tmp_path,
):
    pins = release.OriginalPins(
        source_commit=COMMIT,
        **{
            field: "a" * 64
            for field in release.OriginalPins.__dataclass_fields__
            if field not in {"source_commit", "image_id"}
        },
        image_id="sha256:" + "a" * 64,
    )
    with pytest.raises(ValueError, match="lacks a required reviewed"):
        release._tools(
            {"src/sinter/__init__.py": b'__version__ = "0.5.4rc4.dev0"\n'}, pins
        )
    assert release.MAX_FILE == 64 * 1024 * 1024
    assert release.MAX_BUNDLE == 256 * 1024 * 1024


@pytest.mark.parametrize(
    "content", [b'{"schema":1,"schema":2}', b'{"bytes":NaN}', b'{"bytes":1.1}']
)
def test_strict_public_json_refuses_duplicates_nonfinite_and_float(content):
    with pytest.raises(ValueError):
        release.strict_json(content)


@pytest.mark.skipif(
    os.name != "posix",
    reason="Physical POSIX special files are not available on this host",
)
@pytest.mark.parametrize("kind", ["symlink", "fifo", "hardlink"])
def test_original_tree_redirects_and_special_entries_refuse(tmp_path, kind):
    root = tmp_path / "scope"
    root.mkdir()
    (root / "regular").write_bytes(b"original")
    if kind == "symlink":
        (root / "link").symlink_to(root / "regular")
    elif kind == "fifo":
        os.mkfifo(root / "pipe")
    else:
        os.link(root / "regular", root / "hardlink")
    with pytest.raises(ValueError):
        release._inventory(root)


def test_historical_default_maps_and_release_notes_preserved():
    assert set(legacy.CANDIDATE_PRIORS) == {"0.5.4rc1", "0.5.4rc2", "0.5.4rc3"}
    assert "actual v0.5.3 package replacement" in dispatch.release_notes(
        "0.5.4rc1", COMMIT
    )
    assert "all three published priors" in dispatch.release_notes("0.5.4rc3", COMMIT)
    assert "historical semantic" in dispatch.release_notes(release.VERSION, COMMIT)
    with pytest.raises(ValueError):
        dispatch.release_notes("0.5.4rc5", COMMIT)


def orchestration_controls(tmp_path, monkeypatch, *, catalogue_count=None):
    """Inject explicit inert gate observers in tests only; not production adapters."""
    context, pins, _result, source = sample(
        tmp_path, monkeypatch, catalogue_count=catalogue_count
    )
    monkeypatch.setattr(release, "verify_original", ORIGINAL_VERIFY)
    from tools import installed_native_container as owner
    from tools import rc4_installed_recovery as recovery
    from tools import rc4_native_handoff_contract as native
    from tools import rc4_replacement_contract as replacement
    from tools import release_manifest

    pins = replace(pins, image_id=owner.IMAGE_ID)
    source[owner.SOURCE_FILE] = b"# Explicit synthetic outer owner pin.\n"
    events = []
    for path in list(context.replacement_candidate.iterdir()):
        if path.name not in {
            release.product_names()[0],
            f"Sinter-{release.VERSION}-linux-x64-test.json",
        }:
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    raw_json(
        context.candidate / "licenses/bundled-dependencies.json",
        {
            "schema": "sinter-native-dependencies/v1",
            "packages": [],
            "account_auth_bundled": True,
            "linux_shared_library_notices_verified": True,
        },
    )
    receipt = {
        "execution": "native",
        "system": "Linux",
        "target_arch": "x64",
        "machine": "x86_64",
        "pointer_bits": 64,
        "signed_by_publisher": False,
        "bundled_dependencies": [],
        "installed_test": {"source_only_test_observer": True},
    }
    monkeypatch.setattr(legacy, "_source", lambda *a: source)
    monkeypatch.setattr(release, "_tools", lambda *a: events.append("trusted-tools"))
    monkeypatch.setattr(
        release, "_source_tree", lambda *a: events.append("fixed-source-tree")
    )
    monkeypatch.setattr(
        release_manifest,
        "verify_target_receipt",
        lambda *a: events.append("actual-target") or receipt,
    )
    monkeypatch.setattr(
        legacy,
        "_native_payload",
        lambda *a: events.append("actual-payload") or pins.native_binary_sha256,
    )
    monkeypatch.setattr(
        legacy,
        "verify_rc3_terminal_notices",
        lambda *a: events.append("actual-notices"),
    )
    monkeypatch.setattr(
        release, "_review", lambda *a: events.append("independent-review")
    )
    results = {
        "workflow": {
            "schema": "sinter-owned-rc4-installed-workflow-admission/v1",
            "source_commit": pins.source_commit,
            "version": release.VERSION,
            "installer_sha256": pins.installer_sha256,
            "package_receipt_sha256": pins.package_receipt_sha256,
            "binary_sha256": pins.native_binary_sha256,
            "app_lifetimes": 2,
            "operations_catalogue": len(source_operations(source)),
            "named_checks": 22,
            "workflow_roles": 13,
        },
        "recovery": {
            "candidate_commit": pins.source_commit,
            "boundary": "candidate",
            "installed_lifetimes": 10,
        },
        "native": {
            "source_commit": pins.source_commit,
            "version": release.VERSION,
            "qualification": "candidate",
            "installer_sha256": pins.installer_sha256,
            "baseline": {"binary_sha256": pins.native_binary_sha256},
        },
        "replacement": {
            "source_commit": pins.source_commit,
            "candidate_installer_sha256": pins.installer_sha256,
        },
    }

    def observed(role):
        def invoke(args):
            events.append(role)
            assert args.source_commit == pins.source_commit
            if role in {"workflow", "recovery"}:
                assert args.proof_root == getattr(context, role)
                assert args.installer_sha256 == pins.installer_sha256
                assert args.package_receipt_sha256 == pins.package_receipt_sha256
            if role == "replacement":
                assert args.candidate == context.replacement_candidate
                assert args.repository == context.replacement_repository
                assert (
                    args.outer_owner_file == release.ROOT / "tools/rc4_replacement.py"
                )
            return copy.deepcopy(results[role])

        return invoke

    module = types.ModuleType("tools.rc4_installed_workflow_contract")
    module.verify_original = observed("workflow")
    monkeypatch.setitem(sys.modules, module.__name__, module)
    host = types.ModuleType("tools.rc4_host_tools")
    host.validate_host_pair = lambda value: events.append("actual-host-pair")
    monkeypatch.setitem(sys.modules, host.__name__, host)
    monkeypatch.setattr(recovery, "verify", observed("recovery"))
    monkeypatch.setattr(native, "verify", observed("native"))
    monkeypatch.setattr(replacement, "verify", observed("replacement"))
    return (
        context,
        pins,
        source,
        events,
        results,
        {
            "workflow": module,
            "recovery": recovery,
            "native": native,
            "replacement": replacement,
        },
    )


ORIGINAL_VERIFY = release.verify_original


def test_original_authorization_refuses_pre_temp_browser_schema(tmp_path, monkeypatch):
    context, pins, _source, events, _results, _modules = orchestration_controls(
        tmp_path, monkeypatch
    )
    raw_json(
        context.native / "handoff-container/browser.json",
        {"schema": "sinter-rc4-native-handoff-browser/v2"},
    )
    with pytest.raises(ValueError, match="owned temp evidence"):
        release.verify_original(context, pins)
    assert all(
        role in events for role in ("workflow", "recovery", "native", "replacement")
    )


@pytest.mark.parametrize("count", [53, 54])
def test_catalogue_alignment_binds_actual_source_count(tmp_path, monkeypatch, count):
    context, pins, source, _events, _results, _modules = orchestration_controls(
        tmp_path, monkeypatch, catalogue_count=count
    )
    operations = source_operations(source)
    assert len(operations) == count
    assert ("campaigns.funding_summary" in {row["id"] for row in operations}) is (
        count == 54
    )
    result = release.verify_original(context, pins)
    assert result["gates"]["workflow"]["operations_catalogue"] == count
    assert result["new_installed_execution"] is False
    notes = release.release_notes(COMMIT, operations_catalogue=count)
    assert f"exact {count}-entry source-declared operation catalogue" in notes
    assert "does not claim that every catalogue operation was executed" in notes
    assert "53 installed workflow operations" not in notes


@pytest.mark.parametrize("count", [53, 54])
@pytest.mark.parametrize("claimed", [52, 55, 53.0, 54.0, True, "54"])
def test_catalogue_alignment_rejects_wrong_or_untyped_gate_count(
    tmp_path, monkeypatch, count, claimed
):
    context, pins, _source, _events, results, _modules = orchestration_controls(
        tmp_path, monkeypatch, catalogue_count=count
    )
    results["workflow"]["operations_catalogue"] = claimed
    with pytest.raises(ValueError, match="one final source/package/binary"):
        release.verify_original(context, pins)


@pytest.mark.parametrize("count,claimed", [(53, 54), (54, 53)])
def test_catalogue_alignment_cannot_relabel_another_supported_profile(
    tmp_path, monkeypatch, count, claimed
):
    context, pins, _source, _events, results, _modules = orchestration_controls(
        tmp_path, monkeypatch, catalogue_count=count
    )
    results["workflow"]["operations_catalogue"] = claimed
    with pytest.raises(ValueError, match="one final source/package/binary"):
        release.verify_original(context, pins)


@pytest.mark.parametrize("count", [53, 54])
def test_public_notes_record_pinned_source_count_and_reject_other_profile(
    tmp_path, monkeypatch, count
):
    _context, pins, _result, _files, manifest, digest = stage_fixture(
        tmp_path, monkeypatch, catalogue_count=count
    )
    notes = manifest.parent / "RELEASE-NOTES.md"
    assert f"exact {count}-entry" in notes.read_text()
    inspected = release.inspect_public(manifest, manifest_sha256=digest, pins=pins)
    assert inspected["release_authorized"] is False
    assert inspected["new_installed_execution"] is False
    notes.write_text(
        release.release_notes(COMMIT, operations_catalogue=107 - count),
        encoding="utf-8",
    )

    def reseal_note(value):
        row = next(row for row in value["assets"] if row["path"] == notes.name)
        row.update(release.record(notes.read_bytes()))

    digest = reseal_stage(manifest, reseal_note)
    with pytest.raises(ValueError, match="source catalogue policy"):
        release.inspect_public(manifest, manifest_sha256=digest, pins=pins)


@pytest.mark.parametrize("count", [52, 55, 53.0, True, "54"])
def test_release_note_count_has_only_the_closed_typed_profiles(count):
    with pytest.raises(ValueError, match="source-declared 53 or 54"):
        release.release_notes(COMMIT, operations_catalogue=count)


def test_rc4_review_check_names_catalogue_without_ui_execution_claim():
    assert "rc4_exact_original_source_catalogue_22_checks_13_roles" in (
        release.REVIEW_CHECKS
    )
    assert "rc4_exact_original_workflow_53_operations_22_checks_13_roles" not in (
        release.REVIEW_CHECKS
    )


def test_fixed_original_orchestration_calls_every_actual_gate_not_saved_booleans(
    tmp_path, monkeypatch
):
    context, pins, _source, events, _results, _modules = orchestration_controls(
        tmp_path, monkeypatch
    )
    result = release.verify_original(context, pins)
    assert events == [
        "trusted-tools",
        *(4 * ["fixed-source-tree"]),
        "actual-target",
        "actual-payload",
        "actual-notices",
        "independent-review",
        "workflow",
        "recovery",
        "native",
        "replacement",
        *(4 * ["actual-host-pair"]),
    ]
    assert result["new_installed_execution"] is False
    assert result["general_ai_quality_qualified"] is False
    assert result["customer_device_acceptance"] is False


@pytest.mark.parametrize("gate", ["workflow", "recovery", "native", "replacement"])
def test_each_fixed_original_gate_failure_prevents_stage(tmp_path, monkeypatch, gate):
    context, pins, _source, events, _results, modules = orchestration_controls(
        tmp_path, monkeypatch
    )

    def first_failure(args):
        events.append(gate + "-refused")
        raise ValueError("First raw " + gate + " failure")

    monkeypatch.setattr(
        modules[gate],
        "verify_original" if gate == "workflow" else "verify",
        first_failure,
    )
    with pytest.raises(ValueError, match="First raw " + gate):
        release.prepare_original(context, tmp_path / "refused-stage", pins)
    assert not (tmp_path / "refused-stage").exists()
    assert events[-1] == gate + "-refused"


@pytest.mark.parametrize(
    "gate,field",
    [
        ("workflow", "source_commit"),
        ("workflow", "binary_sha256"),
        ("workflow", "package_receipt_sha256"),
        ("workflow", "operations_catalogue"),
        ("workflow", "named_checks"),
        ("workflow", "workflow_roles"),
        ("recovery", "boundary"),
        ("recovery", "candidate_commit"),
        ("native", "qualification"),
        ("native", "installer_sha256"),
        ("replacement", "candidate_installer_sha256"),
    ],
)
def test_each_gate_must_bind_one_actual_final_identity_and_scope(
    tmp_path, monkeypatch, gate, field
):
    context, pins, _source, _events, results, _modules = orchestration_controls(
        tmp_path, monkeypatch
    )
    results[gate][field] = "wrong-or-development-identity"
    with pytest.raises(ValueError, match="one final source/package/binary"):
        release.verify_original(context, pins)


def test_complete_trusted_tool_manifest_still_cannot_import_different_actual_code(
    tmp_path, monkeypatch
):
    _context, pins, source, _events, _results, _modules = orchestration_controls(
        tmp_path, monkeypatch
    )
    monkeypatch.setattr(release, "_tools", ORIGINAL_TOOLS)
    pins = replace(pins, tool_manifest_sha256=release.tool_manifest(source))
    with pytest.raises(
        ValueError, match="running trusted verifier|complete trusted final source"
    ):
        release._tools(source, pins)


ORIGINAL_TOOLS = release._tools


def test_outer_archive_can_exceed_member_limit_without_weakening_blob_bounds(
    tmp_path, monkeypatch
):
    context, pins, _result, _files = sample(tmp_path, monkeypatch)
    # Two actual bounded test blobs; no installed product or source replay claim.
    for index, scope in enumerate(("workflow", "recovery")):
        (context.roots()[scope] / ("random-" + str(index))).write_bytes(
            os.urandom(32 * 1024 * 1024)
        )
    manifest = release.prepare_original(
        context, tmp_path / "larger-encoded-stage", pins
    )
    encoded = manifest.parent / f"sinter-{release.VERSION}-qualification.zip"
    assert release.MAX_FILE < encoded.stat().st_size < release.MAX_BUNDLE
    with pytest.raises(ValueError, match="member size"):
        release.regular(encoded)
    observed = release.inspect_public(
        manifest, manifest_sha256=release.sha(release.regular(manifest)), pins=pins
    )
    assert observed["historical_semantic_replay"] is False
    with zipfile.ZipFile(io.BytesIO(release._asset_bytes(encoded))) as archive:
        assert all(row.file_size <= release.MAX_FILE for row in archive.infolist())
        assert sum(row.file_size for row in archive.infolist()) <= release.MAX_BUNDLE


@pytest.mark.parametrize("name", list(release.OriginalPins.__dataclass_fields__))
def test_portable_typed_external_pin_fields_refuse_bool_or_missing_identity(name):
    values = {field: "a" * 64 for field in release.OriginalPins.__dataclass_fields__}
    values.update(source_commit=COMMIT, image_id="sha256:" + "a" * 64)
    values[name] = True
    with pytest.raises(ValueError):
        release.OriginalPins(**values).validate()


def test_portable_missing_physical_reader_refuses_without_fallback(
    tmp_path, monkeypatch
):
    path = tmp_path / "safe.txt"
    path.write_bytes(b"source-only test")
    monkeypatch.setattr(release.transport, "physical_reader_supported", lambda: False)
    with pytest.raises(release.transport.UnsupportedReader, match="POSIX"):
        release.regular(path)


def test_portable_exact_version_dispatch_keeps_legacy_policy_refusal(
    tmp_path, monkeypatch
):
    with pytest.raises(ValueError, match="no explicit qualification"):
        legacy._identity(release.VERSION, COMMIT)
    manifest = tmp_path / "candidate-release-manifest.json"
    raw_json(
        manifest,
        {
            "schema": release.SCHEMA,
            "version": release.VERSION,
            "source_commit": COMMIT,
            "repository": legacy.REPOSITORY,
            "tag": "v" + release.VERSION,
            "prerelease": True,
            "latest": False,
            "qualified_targets": [legacy.TARGET],
            "unqualified_targets": legacy.UNQUALIFIED,
            "all_platform_release_qualified": False,
            "publication_executed": False,
            "original_authorization_required": True,
            "historical_semantic_replay": False,
            "new_installed_execution": False,
        },
    )
    observed = []
    monkeypatch.setattr(
        release,
        "authorize_original",
        lambda path, **kwargs: observed.append(kwargs) or {"version": release.VERSION},
    )
    assert (
        dispatch.verify_plan(
            manifest,
            rc4_context="inert explicit test context",
            rc4_pins="inert explicit test pins",
            rc4_manifest_sha256="b" * 64,
        )["version"]
        == release.VERSION
    )
    assert observed == [
        {
            "context": "inert explicit test context",
            "pins": "inert explicit test pins",
            "manifest_sha256": "b" * 64,
        }
    ]


def review_controls(tmp_path, monkeypatch):
    context, pins, _result, _source = sample(tmp_path, monkeypatch)
    (context.independent_review / "retained.txt").unlink()
    shutil.rmtree(context.independent_review / "empty-directory")
    installed = {"source_only_synthetic_clean_observer": True}
    raw_json(context.independent_review / "clean-ubuntu-installed-test.json", installed)
    raw_json(
        context.independent_review / "qualification-context.json",
        {
            "source_commit": pins.source_commit,
            "version": release.VERSION,
            "installer_sha256": pins.installer_sha256,
            "container": "ubuntu:22.04",
            "network": "disabled",
            "host_installation": False,
            "product_edits": False,
            "preinstalled_python": False,
            "preinstalled_account_packages": False,
        },
    )
    (context.independent_review / "clean-ubuntu-installed-test.log").write_bytes(
        b"Explicit synthetic source-only complete raw log observer.\n"
    )
    files = release._inventory(context.independent_review)["files"]
    review = {
        "schema": release.REVIEW_SCHEMA,
        "version": release.VERSION,
        "source_commit": pins.source_commit,
        "checks": {name: True for name in release.REVIEW_CHECKS},
        "raw_files": {name: files[name] for name in legacy.REVIEW_FILES[1:]},
    }
    for name in (
        "installer_sha256",
        "native_archive_sha256",
        "source_archive_sha256",
        "portable_sha256",
        "native_binary_sha256",
        "tool_manifest_sha256",
    ):
        review[name] = getattr(pins, name)
    raw_json(context.independent_review / "final-artifact-review.json", review)
    pins = replace(
        pins,
        independent_review_sha256=release.sha(
            release.regular(context.independent_review / "final-artifact-review.json")
        ),
    )
    return context, pins, {"installed_test": installed}, review


def test_independent_review_requires_complete_raw_records_not_only_checks(
    tmp_path, monkeypatch
):
    context, pins, receipt, _review = review_controls(tmp_path, monkeypatch)
    release._review(context, pins, receipt)
    (context.independent_review / "clean-ubuntu-installed-test.log").write_bytes(
        b"different raw command output"
    )
    with pytest.raises(ValueError, match="raw evidence is not bound"):
        release._review(context, pins, receipt)


@pytest.mark.parametrize(
    "change",
    [
        "raw-null",
        "raw-missing",
        "raw-extra",
        "checks-bool-as-int",
        "checks-missing",
        "another-binary",
        "another-commit",
        "another-schema",
        "changed-clean",
        "wrong-context-type",
    ],
)
def test_independent_review_mutations_refuse_before_gate_calls(
    tmp_path, monkeypatch, change
):
    context, pins, receipt, review = review_controls(tmp_path, monkeypatch)
    if change == "raw-null":
        review["raw_files"] = None
    elif change == "raw-missing":
        review["raw_files"].pop("qualification-context.json")
    elif change == "raw-extra":
        review["raw_files"]["extra"] = {"bytes": 0, "sha256": "a" * 64}
    elif change == "checks-bool-as-int":
        review["checks"][release.REVIEW_CHECKS[0]] = 1
    elif change == "checks-missing":
        review["checks"].pop(release.REVIEW_CHECKS[0])
    elif change == "another-binary":
        review["native_binary_sha256"] = "e" * 64
    elif change == "another-commit":
        review["source_commit"] = "e" * 40
    elif change == "another-schema":
        review["schema"] = "sinter-independent-final-artifact-review/v1"
    elif change == "changed-clean":
        receipt["installed_test"] = {"other": True}
    elif change == "wrong-context-type":
        raw_json(
            context.independent_review / "qualification-context.json",
            {
                "source_commit": pins.source_commit,
                "version": release.VERSION,
                "installer_sha256": pins.installer_sha256,
                "container": "ubuntu:22.04",
                "network": "disabled",
                "host_installation": 0,
                "product_edits": False,
                "preinstalled_python": False,
                "preinstalled_account_packages": False,
            },
        )
        review["raw_files"]["qualification-context.json"] = release.record(
            release.regular(context.independent_review / "qualification-context.json")
        )
    raw_json(context.independent_review / "final-artifact-review.json", review)
    pins = replace(
        pins,
        independent_review_sha256=release.sha(
            release.regular(context.independent_review / "final-artifact-review.json")
        ),
    )
    with pytest.raises(ValueError):
        release._review(context, pins, receipt)


def test_forbidden_actual_external_executable_payload_cannot_export(
    tmp_path, monkeypatch
):
    context, pins, _result, _source = sample(tmp_path, monkeypatch)
    payload = (
        b"Synthetic externally observed executable identity, not customer runtime.\n"
    )
    (context.workflow / "external-tool-copy").write_bytes(payload)
    for version in ("0.5.3", "0.5.4rc1", "0.5.4rc2", "0.5.4rc3"):
        path = context.replacement / version / "outer.json"
        value = release.strict_json(release.regular(path))
        value["host"]["before"]["tools"]["docker"]["sha256"] = release.sha(payload)
        raw_json(path, value)
    with pytest.raises(ValueError, match="must not be exported"):
        release.prepare_original(context, tmp_path / "refused-stage", pins)
    assert not (tmp_path / "refused-stage").exists()


def test_failed_stage_retains_original_error_and_all_unpublished_copied_bytes(
    tmp_path, monkeypatch
):
    context, pins, _result, _source = sample(tmp_path, monkeypatch)
    copied, original_copy = [], shutil.copyfile
    first = OSError("Actual second staged product copy failed")

    def copy_file(source, target):
        if copied:
            raise first
        original_copy(source, target)
        copied.append(Path(target))

    monkeypatch.setattr(shutil, "copyfile", copy_file)
    with pytest.raises(OSError) as observed:
        release.prepare_original(context, tmp_path / "unpublished-stage", pins)
    assert observed.value is first
    partial = Path(first.rc4_unpublished_stage)
    assert partial.is_dir() and copied[0].exists()
    assert (
        copied[0].read_bytes()
        == (context.candidate / release.product_names()[0]).read_bytes()
    )
    assert not (tmp_path / "unpublished-stage").exists()


def test_owned_zip_close_cannot_replace_primary_write_error(monkeypatch, tmp_path):
    first, closing = (
        OSError("First bundle write error"),
        OSError("Additional bundle close error"),
    )

    class InertZip:
        def __init__(self, *args, **kwargs):
            pass

        def close(self):
            raise closing

    monkeypatch.setattr(zipfile, "ZipFile", InertZip)
    with pytest.raises(OSError) as observed:
        with release._writing_bundle(tmp_path / "source-only-inert.zip"):
            raise first
    assert observed.value is first
    assert observed.value.rc4_secondary_errors == (closing,)


def test_owned_zip_close_failure_without_primary_is_not_silently_ignored(
    monkeypatch, tmp_path
):
    closing = OSError("Bundle close failed without an earlier error")

    class InertZip:
        def __init__(self, *args, **kwargs):
            pass

        def close(self):
            raise closing

    monkeypatch.setattr(zipfile, "ZipFile", InertZip)
    with pytest.raises(OSError) as observed:
        with release._writing_bundle(tmp_path / "source-only-inert.zip"):
            pass
    assert observed.value is closing
