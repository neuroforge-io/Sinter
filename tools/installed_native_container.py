"""Own one offline Linux native-entry container, or a separate safe mechanics run.

Only fixed Docker/source-verifier commands are used. No image pull/build, login,
provider, user display or installer build is performed. Mechanics never invokes
Sinter or installs a package and cannot produce a native-entry admission.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import platform
import secrets
import shutil
import signal
import stat
import sys
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "src"))
from tools import installed_native_entry_contract as contract  # noqa: E402
from tools import installed_native_menu as inner  # noqa: E402

IMAGE_ID = "sha256:a6abf8768b5d981009b5fd68c7663ed14f87ade82ba8e5aa9be7f856f9313268"
MECHANICS_SCHEMA = "sinter-owned-native-entry-mechanics/v1"
CANARY = b"Fictional native-entry container mechanics; no Sinter or installer run.\n"
SOURCE_FILE = "tools/installed_native_container.py"
REQUIRED_TOOLS = ("git", "dpkg", "dpkg-deb", "dpkg-query", "Xvfb", "xauth")
INSTALLED_PATHS = [
    "/opt/neuroforge/sinter/Sinter",
    "/usr/share/applications/sinter.desktop",
    "/usr/share/applications/sinter-native.desktop",
]


def write_json(path, value):
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def source_records(source):
    records = {}
    for path in sorted(source.rglob("*")):
        contract.require(
            "__pycache__" not in path.parts and path.suffix != ".pyc",
            "Source snapshot must not contain import caches.",
        )
        if path.is_dir():
            contract.require(
                not path.is_symlink(), "Source directories must not redirect."
            )
            continue
        raw = inner.regular_bytes(path, inner.MAX_MEMBER)
        contract.require(
            len(records) < inner.MAX_ENTRIES, "Source snapshot has too many paths."
        )
        records[str(path.relative_to(source))] = {
            "bytes": len(raw),
            "sha256": contract.sha(raw),
        }
    contract.require(SOURCE_FILE in records, "The exact outer source is missing.")
    return records


def records_hash(records):
    return contract.sha(
        json.dumps(
            records, sort_keys=True, separators=(",", ":"), allow_nan=False
        ).encode()
    )


def prepare(args):
    contract.require(
        platform.system() == "Linux", "The outer owner supports this Linux host only."
    )
    inner.exact_text(args.owner_sha256, r"[0-9a-f]{64}", "reviewed outer source")
    contract.require(
        contract.sha(inner.regular_bytes(ROOT / SOURCE_FILE, 2 * 1024 * 1024))
        == args.owner_sha256,
        "Outer source differs from the supplied independent review pin.",
    )
    output = args.output.resolve()
    contract.require(
        not os.path.lexists(output), "Use a new owned root, never an existing output."
    )
    inputs = [ROOT]
    if args.mode in {"run", "run-archive"}:
        contract.require(
            all(
                getattr(args, key, None) is not None
                for key in (
                    "repository",
                    "source_commit",
                    "installer",
                    "package_receipt",
                )
            ),
            "The installed route requires exact source/package.",
        )
        inputs += [
            args.repository.resolve(),
            args.installer.parent.resolve(),
            args.package_receipt.parent.resolve(),
        ]
    contract.require(
        all(
            output != path
            and not output.is_relative_to(path)
            and not path.is_relative_to(output)
            for path in inputs
        ),
        "Owned output must be outside all inputs and their ancestors.",
    )
    parent = output.parent.stat()
    contract.require(
        stat.S_ISDIR(parent.st_mode)
        and parent.st_uid == os.geteuid()
        and not parent.st_mode & 0o022,
        "Use an owned non-shared output parent.",
    )
    output.mkdir(mode=0o700)
    for name in ("source", "repository", "candidate", "out", "tmp", "client", "raw"):
        (output / name).mkdir(
            mode=0o755 if name in {"source", "repository", "candidate"} else 0o700
        )
    # Parent 0700 keeps this mount private on the host. Container root with
    # all capabilities dropped needs ordinary write permission in /out.
    (output / "out").chmod(0o777)
    (output / "client/.docker").mkdir(mode=0o700)
    env = {
        "PATH": os.defpath,
        "LANG": "C.UTF-8",
        "LC_ALL": "C.UTF-8",
        "HOME": str(output / "client"),
        "DOCKER_CONFIG": str(output / "client/.docker"),
        "TMPDIR": str(output / "tmp"),
        "PYTHONDONTWRITEBYTECODE": "1",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
    }
    records = source_records(ROOT)
    for name in records:
        target = output / "source" / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(inner.regular_bytes(ROOT / name, inner.MAX_MEMBER))
    contract.exact(
        source_records(output / "source"), records, "Fresh staged source bytes differ."
    )
    return output, env, records


def capture(role, argv, root, env, rows, *, timeout=20, limit=65536):
    code, raw = inner.command(
        argv,
        rows,
        env=env,
        timeout=timeout,
        limit=limit,
        save_streams={
            key: root / "raw" / (role + "." + key) for key in ("stdout", "stderr")
        },
    )
    return code, raw


def docker_row(role, argv, root, env, commands, client_rows, *, timeout=20):
    before = len(client_rows)
    try:
        return capture(role, argv, root, env, client_rows, timeout=timeout)
    finally:
        if len(client_rows) > before:
            row = client_rows[-1]
            commands.append(
                {
                    "role": role,
                    "argv": list(argv),
                    "exit_code": row.get("exit_code"),
                    "stdout": row.get("stdout"),
                    "stderr": row.get("stderr"),
                    "reaped": row.get("streams_complete", False),
                }
            )


def client_identity(root, env, rows):
    path = Path(shutil.which("docker", path=os.defpath) or "/missing-docker").resolve(
        strict=True
    )
    raw = inner.regular_bytes(path, inner.MAX_MEMBER)
    code, version = capture("client-version", ["docker", "--version"], root, env, rows)
    contract.require(code == 0, "Actual Docker client version could not be observed.")
    contract.quiet(rows[-1]["stderr"])
    contract.require(
        version.startswith(b"Docker version ")
        and version.endswith(b"\n")
        and len(version) < 200,
        "Actual Docker client identity is unexpected.",
    )
    return {"path": str(path), "sha256": contract.sha(raw), "version": rows[-1]}


def mechanics_argv(pins, name):
    argv = contract.outer_argv(pins, name)
    index = argv.index(pins["image_id"])
    return argv[: index + 1] + [
        "python3",
        "-B",
        "/source/" + SOURCE_FILE,
        "_mechanics_inside",
    ]


def validate_mechanics(bundle, pins):
    contract.require(
        type(bundle) is dict
        and set(bundle)
        == {
            "schema",
            "owner_sha256",
            "source_manifest",
            "source_manifest_sha256",
            "docker_client",
            "commands",
        },
        "Require the complete mechanics-only bundle.",
    )
    contract.exact(
        bundle["schema"],
        MECHANICS_SCHEMA,
        "Mechanics cannot substitute for installed ownership.",
    )
    contract.exact(
        bundle["owner_sha256"],
        pins["outer_owner_sha256"],
        "Mechanics owner differs from the independent source pin.",
    )
    contract.require(
        records_hash(bundle["source_manifest"]) == bundle["source_manifest_sha256"],
        "Mechanics source manifest hash differs.",
    )
    contract.require(
        bundle["source_manifest"][SOURCE_FILE]["sha256"] == pins["outer_owner_sha256"],
        "Mechanics source did not contain the pinned actual owner.",
    )
    result = contract._validate_lifecycle(bundle["commands"], pins, mechanics_argv)
    observed = contract.json_object(result["start_stdout"])
    contract.require(
        set(observed)
        == {
            "schema",
            "os_release",
            "system",
            "machine",
            "euid",
            "interfaces",
            "pid",
            "cwd",
            "installed_paths",
            "canary_sha256",
            "source_manifest_sha256",
            "tool_paths",
        },
        "Actual mechanics observations are incomplete or unknown.",
    )
    contract.exact(
        {
            key: observed[key]
            for key in (
                "schema",
                "system",
                "machine",
                "euid",
                "interfaces",
                "pid",
                "cwd",
                "installed_paths",
                "canary_sha256",
                "source_manifest_sha256",
            )
        },
        {
            "schema": "sinter-native-entry-container-mechanics-observation/v1",
            "system": "Linux",
            "machine": "x86_64",
            "euid": 0,
            "interfaces": ["lo"],
            "pid": 1,
            "cwd": "/",
            "installed_paths": [
                {"path": path, "lexists": False} for path in INSTALLED_PATHS
            ],
            "canary_sha256": contract.sha(CANARY),
            "source_manifest_sha256": bundle["source_manifest_sha256"],
        },
        "Actual mechanics isolation/canary/source observations differ.",
    )
    tool_paths = observed["tool_paths"]
    contract.require(
        type(tool_paths) is dict
        and set(tool_paths) == set(REQUIRED_TOOLS)
        and all(
            value is None or (type(value) is str and Path(value).is_absolute())
            for value in tool_paths.values()
        ),
        "Complete actual image tool paths are missing.",
    )
    os_release = contract.full_bytes(observed["os_release"]).decode("utf-8")
    fields = dict(line.split("=", 1) for line in os_release.splitlines() if "=" in line)
    contract.require(
        fields.get("ID") == "ubuntu" and fields.get("VERSION_ID") == '"22.04"',
        "Actual image runtime is not Ubuntu 22.04.",
    )
    identity = bundle["docker_client"]
    contract.require(
        type(identity) is dict
        and set(identity) == {"path", "sha256", "version", "sha256_after"},
        "Complete actual Docker client evidence is missing.",
    )
    contract.exact(
        identity["sha256_after"],
        identity["sha256"],
        "Docker client changed during the mechanics run.",
    )
    inner.exact_text(identity["sha256"], r"[0-9a-f]{64}", "actual Docker client bytes")
    contract.require(
        type(identity["path"]) is str and Path(identity["path"]).is_absolute(),
        "Actual Docker client path is missing.",
    )
    row = identity["version"]
    contract.stopped(row)
    contract.quiet(row["stderr"])
    contract.exact(
        row["argv"],
        ["docker", "--version"],
        "Actual Docker client version command differs.",
    )
    contract.exact(
        row.get("streams_complete"),
        True,
        "Docker version streams were captured before reap.",
    )
    contract.require(
        contract.stream_bytes(row["stdout"]).startswith(b"Docker version "),
        "Actual Docker version output is missing.",
    )
    return {
        "schema": "sinter-native-entry-container-mechanics-verified/v1",
        "image_id": pins["image_id"],
        "container_id": result["container_id"],
        "owner_sha256": pins["outer_owner_sha256"],
        "installed_tooling_available": all(
            tool_paths[key] is not None for key in REQUIRED_TOOLS
        ),
        "actual_tool_paths": tool_paths,
        "scope": "Actual container mechanics only; no Sinter/DEB, installed/native-entry or release admission",
    }


def require_installed_tooling(evidence, source_route="git"):
    """Derive this guard from the verified original tool observations, not a passed flag."""
    contract.require(
        source_route in {"git", "archive"}, "Unsupported source tooling route."
    )
    paths = evidence.get("actual_tool_paths")
    contract.require(
        type(paths) is dict
        and set(paths) == set(REQUIRED_TOOLS)
        and all(
            type(paths[key]) is str and Path(paths[key]).is_absolute()
            for key in REQUIRED_TOOLS
            if key != "git" or source_route == "git"
        ),
        "Actual reviewed image lacks installed-owner tooling; do not start the native producer.",
    )


def mechanics_inside():
    contract.require(
        platform.system() == "Linux"
        and os.geteuid() == 0
        and Path("/.dockerenv").is_file()
        and os.getpid() == 1
        and os.getcwd() == "/"
        and {path.name for path in Path("/sys/class/net").iterdir()} == {"lo"}
        and not os.environ.get("DISPLAY")
        and not os.environ.get("XAUTHORITY"),
        "Mechanics require the exact owned offline root container.",
    )
    contract.require(
        Path("/source").resolve() == Path("/source"),
        "Mechanics source must not redirect.",
    )
    raw = inner.regular_bytes(Path("/etc/os-release").resolve(strict=True), 128000)
    fields = dict(
        line.split("=", 1) for line in raw.decode().splitlines() if "=" in line
    )
    contract.require(
        fields.get("ID") == "ubuntu" and fields.get("VERSION_ID") == '"22.04"',
        "Mechanics image is not actual Ubuntu 22.04.",
    )
    contract.require(
        inner.regular_bytes(Path("/candidate/mechanics-input.txt"), 1000) == CANARY
        and inner.regular_bytes(Path("/repository/mechanics-input.txt"), 1000)
        == CANARY,
        "Private read-only canary inputs differ.",
    )
    paths = [
        {"path": path, "lexists": os.path.lexists(path)} for path in INSTALLED_PATHS
    ]
    contract.require(
        all(row["lexists"] is False for row in paths),
        "Mechanics must not inherit Sinter installed paths.",
    )
    records = source_records(Path("/source"))
    # The only write is a fictional literal into this fresh private output mount.
    destination = Path("/out/mechanics-canary.txt")
    with destination.open("xb") as stream:
        stream.write(CANARY)
    print(
        json.dumps(
            {
                "schema": "sinter-native-entry-container-mechanics-observation/v1",
                "tool_paths": {
                    key: str(Path(found).resolve(strict=True))
                    if (found := shutil.which(key))
                    else None
                    for key in REQUIRED_TOOLS
                },
                "os_release": {
                    "bytes": len(raw),
                    "sha256": contract.sha(raw),
                    "base64": base64.b64encode(raw).decode(),
                },
                "system": platform.system(),
                "machine": platform.machine(),
                "euid": os.geteuid(),
                "interfaces": sorted(
                    path.name for path in Path("/sys/class/net").iterdir()
                ),
                "pid": os.getpid(),
                "cwd": os.getcwd(),
                "installed_paths": paths,
                "canary_sha256": contract.sha(destination.read_bytes()),
                "source_manifest_sha256": records_hash(records),
            },
            sort_keys=True,
        )
    )
    return 0


def pins_for(
    root,
    owner_sha,
    commit="0" * 40,
    installer_name="mechanics-input.txt",
    receipt_name="mechanics-expected.txt",
):
    return {
        "image_id": IMAGE_ID,
        "outer_owner_sha256": owner_sha,
        "source_commit": commit,
        "source_directory": str(root / "source"),
        "repository": str(root / "repository"),
        "candidate_directory": str(root / "candidate"),
        "output_directory": str(root / "out"),
        "installer_name": installer_name,
        "package_receipt_name": receipt_name,
    }


def evidence_pins(bundle):
    # Derive paths from the actual create argv, then validate every argv/mount/raw
    # lifecycle record against that same fixed mechanics invocation.
    argv = bundle["commands"][1]["argv"]
    mounts = [argv[index + 1] for index, value in enumerate(argv) if value == "--mount"]
    host = {}
    for mount in mounts:
        fields = dict(item.split("=", 1) for item in mount.split(",") if "=" in item)
        host[fields["dst"]] = fields["src"]
    contract.require(
        set(host) == {"/source", "/repository", "/candidate", "/out"},
        "Mechanics evidence has another mount set.",
    )
    root = Path(host["/source"]).parent
    pins = pins_for(root, bundle["owner_sha256"])
    contract.exact(
        [host[key] for key in ("/source", "/repository", "/candidate", "/out")],
        [
            pins[key]
            for key in (
                "source_directory",
                "repository",
                "candidate_directory",
                "output_directory",
            )
        ],
        "Mechanics did not own its four sibling private trees.",
    )
    return pins


def lifecycle(root, env, pins, commands, rows, *, mechanics=False, cleanup_rows=None):
    identifier = None
    exited = False
    if cleanup_rows is None:
        cleanup_rows = []
    body_error = None
    try:
        code, image_raw = docker_row(
            "image", ["docker", "image", "inspect", IMAGE_ID], root, env, commands, rows
        )
        contract.require(
            code == 0, "Reviewed local image is unavailable; never pull or replace it."
        )
        contract.validate_image(image_raw, pins)
        name = "sinter-native-entry-" + secrets.token_hex(6)
        argv = (
            mechanics_argv(pins, name) if mechanics else contract.outer_argv(pins, name)
        )
        code, raw = docker_row("create", argv, root, env, commands, rows)
        contract.require(code == 0, "Actual owned container could not be created.")
        identifier = raw.decode("ascii").strip()
        inner.exact_text(identifier, r"[0-9a-f]{64}", "owned container")
        contract.require(
            raw == (identifier + "\n").encode(),
            "Actual create ID response is not exact.",
        )
        code, created_raw = docker_row(
            "created", ["docker", "inspect", identifier], root, env, commands, rows
        )
        contract.require(code == 0, "Actual created container could not be inspected.")
        created = json.loads(created_raw, object_pairs_hook=contract.unique)
        contract.require(
            type(created) is list and len(created) == 1,
            "Require one actual created container.",
        )
        contract.validate_container_observation(
            created[0],
            pins,
            mechanics_argv if mechanics else contract.outer_argv,
            name,
            identifier,
            "created",
        )
        code, _ = docker_row(
            "start",
            ["docker", "start", "-a", identifier],
            root,
            env,
            commands,
            rows,
            timeout=180 if not mechanics else 30,
        )
        # Inspect exit even when the actual fixed producer itself failed.
        inspect_code, raw = docker_row(
            "exited", ["docker", "inspect", identifier], root, env, commands, rows
        )
        contract.require(
            inspect_code == 0, "Actual container exit could not be inspected."
        )
        state = json.loads(raw)[0]["State"]
        exited = state.get("Running") is False and state.get("Status") == "exited"
        contract.require(
            code == 0 and exited, "Owned container producer failed or remains running."
        )
    except BaseException as error:
        body_error = error
    finally:
        if identifier is not None:
            try:
                if not exited:
                    # Never use a name, wildcard, host PID or unrelated resource.
                    # Escalation preserves failure; it cannot create admission.
                    for role, argv in (
                        (
                            "cleanup-term",
                            ["docker", "kill", "--signal", "SIGTERM", identifier],
                        ),
                        ("cleanup-wait", ["docker", "wait", identifier]),
                    ):
                        try:
                            capture(role, argv, root, env, cleanup_rows, timeout=8)
                        except BaseException:
                            pass
                argv = (
                    ["docker", "rm", identifier]
                    if exited
                    else ["docker", "rm", "-f", identifier]
                )
                code, _ = docker_row("remove", argv, root, env, commands, rows)
                contract.require(code == 0, "Owned container removal failed.")
                code, _ = docker_row(
                    "removed",
                    ["docker", "inspect", identifier],
                    root,
                    env,
                    commands,
                    rows,
                )
                contract.require(code == 1, "Owned container absence was not observed.")
                contract.validate_removal(commands[-2], commands[-1], identifier)
            except BaseException as cleanup_error:
                cleanup_rows.append(
                    {
                        "schema": "sinter-owned-container-cleanup-error/v1",
                        "container_id": identifier,
                        "error_type": type(cleanup_error).__name__,
                        "error": str(cleanup_error)[:4096],
                    }
                )
                if body_error is None:
                    body_error = cleanup_error
    if body_error:
        raise body_error
    return identifier


def run(args):
    root, env, records = prepare(args)
    context = {
        "schema": "sinter-native-entry-container-owner-run/v1",
        "mode": args.mode,
        "owner_sha256": args.owner_sha256,
        "image_id": IMAGE_ID,
        "source_manifest_sha256": records_hash(records),
        "source_manifest": records,
        "installed_admission": None,
        "mechanics_verification": None,
    }
    rows, commands, cleanup_rows = [], [], []
    try:
        client = client_identity(root, env, rows)
        if args.mode == "mechanics":
            for path in (
                root / "repository/mechanics-input.txt",
                root / "candidate/mechanics-input.txt",
                root / "candidate/mechanics-expected.txt",
            ):
                path.write_bytes(CANARY)
            pins = pins_for(root, args.owner_sha256)
        else:
            source = inner.source_identity(args.repository, args.source_commit, rows)
            package = inner.package_preflight(args, source, rows)
            contract.json_object(
                inner.regular_bytes(args.package_receipt, 2 * 1024 * 1024)
            )
            code, _ = capture(
                "clone",
                [
                    "git",
                    "clone",
                    "--bare",
                    "--no-local",
                    "--no-hardlinks",
                    "--",
                    str(args.repository.resolve()),
                    str(root / "repository"),
                ],
                root,
                env,
                rows,
                timeout=60,
            )
            contract.require(code == 0, "Fresh private Git object copy failed.")
            for input_file in (args.installer, args.package_receipt):
                (root / "candidate" / input_file.name).write_bytes(
                    inner.regular_bytes(input_file, inner.MAX_ARCHIVE)
                )
            contract.exact(
                inner.source_identity(root / "repository", args.source_commit, rows),
                source,
                "Private Git source differs after copying.",
            )
            pins = pins_for(
                root,
                args.owner_sha256,
                args.source_commit,
                args.installer.name,
                args.package_receipt.name,
            )
            source_route = "archive" if args.mode == "run-archive" else "git"
            pins["source_route"] = source_route
            if source_route == "archive":
                code, archive = capture(
                    "stage-source-archive",
                    [
                        "git",
                        "-C",
                        str(root / "repository"),
                        "archive",
                        args.source_commit,
                    ],
                    root,
                    env,
                    rows,
                    timeout=30,
                    limit=inner.MAX_ARCHIVE,
                )
                contract.require(
                    code == 0 and contract.sha(archive) == source["archive_sha256"],
                    "Fresh actual bare-repo archive differs.",
                )
                contract.exact(
                    inner.strict_archive(archive, args.source_commit),
                    source,
                    "Staged complete source differs from actual bare repository.",
                )
                (root / "repository" / inner.ARCHIVE_NAME).write_bytes(archive)
                write_json(
                    root / "repository" / inner.ORIGIN_NAME,
                    inner.archive_origin(source, len(archive)),
                )
            # Fresh actual same-image mechanics are owned here, never supplied
            # as a self-declared prior receipt or substituted for native work.
            mechanics_args = SimpleNamespace(
                mode="mechanics",
                output=root / "image-proof",
                owner_sha256=args.owner_sha256,
            )
            image_result = run(mechanics_args)
            contract.require(
                image_result.get("mechanics_verification") is not None
                and "error_type" not in image_result,
                "Fresh actual same-image mechanics refused; do not start the installed producer.",
            )
            image_file = root / "image-proof/container-mechanics.json"
            image_evidence = contract.json_object(
                inner.regular_bytes(image_file, 16 * 1024 * 1024)
            )
            evidence = validate_mechanics(image_evidence, evidence_pins(image_evidence))
            require_installed_tooling(evidence, source_route)
            contract.exact(
                evidence["owner_sha256"],
                args.owner_sha256,
                "Actual image mechanics came from another source pin.",
            )
            contract.exact(
                evidence["image_id"], IMAGE_ID, "Actual mechanics image differs."
            )
            contract.exact(
                image_evidence["docker_client"]["sha256"],
                client["sha256"],
                "Actual Docker client changed between owned image/native runs.",
            )
            context["image_mechanics"] = evidence
            context.update(
                source=source,
                package=package,
                image_evidence_sha256=contract.sha(
                    inner.regular_bytes(image_file, 16 * 1024 * 1024)
                ),
            )
        for tree in (root / "source", root / "repository", root / "candidate"):
            for path in tree.rglob("*"):
                contract.require(
                    not path.is_symlink(), "Staged readonly inputs must not redirect."
                )
                path.chmod(0o555 if path.is_dir() else 0o444)
            tree.chmod(0o555)
        identifier = lifecycle(
            root,
            env,
            pins,
            commands,
            rows,
            mechanics=args.mode == "mechanics",
            cleanup_rows=cleanup_rows,
        )
        contract.exact(
            source_records(root / "source"),
            records,
            "Read-only staged source changed during execution.",
        )
        client["sha256_after"] = contract.sha(
            inner.regular_bytes(Path(client["path"]), inner.MAX_MEMBER)
        )
        contract.exact(
            client["sha256_after"],
            client["sha256"],
            "Actual Docker client changed during execution.",
        )
        if args.mode == "mechanics":
            bundle = {
                "schema": MECHANICS_SCHEMA,
                "owner_sha256": args.owner_sha256,
                "source_manifest": records,
                "source_manifest_sha256": records_hash(records),
                "docker_client": client,
                "commands": commands,
            }
            contract.require(
                inner.regular_bytes(root / "out/mechanics-canary.txt", 1000) == CANARY,
                "Actual output canary changed.",
            )
            context["mechanics_verification"] = validate_mechanics(bundle, pins)
            write_json(root / "container-mechanics.json", bundle)
        else:
            for field, path in (
                ("installer_sha256", root / "candidate" / args.installer.name),
                ("receipt_sha256", root / "candidate" / args.package_receipt.name),
            ):
                contract.require(
                    contract.sha(inner.regular_bytes(path, inner.MAX_ARCHIVE))
                    == package[field],
                    "Read-only candidate bytes changed during execution.",
                )
            raw_inner = inner.regular_bytes(
                root / "out/native-entry/installed-native-entry-test.json",
                16 * 1024 * 1024,
            )
            pins["artifacts"] = {
                "inner_receipt_sha256": contract.sha(raw_inner),
                "source_archive_sha256": source["archive_sha256"],
                "installer_sha256": package["installer_sha256"],
                "package_receipt_sha256": package["receipt_sha256"],
            }
            if source_route == "archive":
                pins["artifacts"]["source_origin_sha256"] = contract.sha(
                    inner.regular_bytes(
                        root / "repository" / inner.ORIGIN_NAME, 2 * 1024 * 1024
                    )
                )
            bundle = {
                "schema": contract.ARCHIVE_OUTER_SCHEMA
                if source_route == "archive"
                else contract.OUTER_SCHEMA,
                "owner_sha256": args.owner_sha256,
                "artifacts": pins["artifacts"],
                "commands": commands,
            }
            write_json(root / "outer-container.json", bundle)
            contract.exact(
                contract.validate_outer(bundle, pins),
                identifier,
                "Closed outer identity differs.",
            )
            argv = [
                sys.executable,
                "-B",
                str(root / "source/tools/installed_native_entry_contract.py"),
                "--receipt",
                str(root / "out/native-entry/installed-native-entry-test.json"),
                "--outer-bundle",
                str(root / "outer-container.json"),
                "--outer-owner-file",
                str(root / "source" / SOURCE_FILE),
                "--outer-owner-sha256",
                args.owner_sha256,
                "--outer-output",
                str(root / "out"),
                "--owned-root",
                str(root),
                "--repository",
                str(root / "repository"),
                "--source-commit",
                args.source_commit,
                "--installer",
                str(root / "candidate" / args.installer.name),
                "--package-receipt",
                str(root / "candidate" / args.package_receipt.name),
                "--image-id",
                IMAGE_ID,
            ]
            code, raw = capture("admission", argv, root, env, rows, timeout=60)
            contract.require(
                code == 0,
                "Closed installed native-entry admission refused actual evidence.",
            )
            admission = contract.json_object(raw)
            contract.exact(
                admission.get("schema"),
                "sinter-installed-native-entry-admission/v1",
                "Actual verifier did not return native-entry admission.",
            )
            contract.exact(
                admission.get("container_id"),
                identifier,
                "Actual admission belongs to another container.",
            )
            contract.exact(
                admission.get("source_commit"),
                args.source_commit,
                "Actual admission belongs to another source.",
            )
            context["installed_admission"] = admission
        return context
    except BaseException as error:
        context.update(error_type=type(error).__name__, error=str(error)[:4096])
        if isinstance(error, (KeyboardInterrupt, SystemExit)):
            raise
        return context
    finally:
        context["commands"] = commands
        context["cleanup_commands"] = cleanup_rows
        write_json(root / "client-commands.json", rows)
        write_json(root / "owner-run.json", context)


def main(argv=None):
    arguments = list(sys.argv[1:] if argv is None else argv)
    if arguments == ["_mechanics_inside"]:
        return mechanics_inside()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("mode", choices=("mechanics", "run", "run-archive"))
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--owner-sha256", required=True)
    for field in ("repository", "installer", "package-receipt"):
        parser.add_argument("--" + field, type=Path)
    parser.add_argument("--source-commit")
    args = parser.parse_args(arguments)
    previous = signal.getsignal(signal.SIGTERM)

    def interrupted(*_):
        raise KeyboardInterrupt("Owned outer run interrupted.")

    signal.signal(signal.SIGTERM, interrupted)
    try:
        result = run(args)
    except (ValueError, OSError, KeyError, TypeError) as error:
        print(
            json.dumps(
                {
                    "schema": "sinter-native-entry-container-owner-refusal/v1",
                    "error": str(error),
                }
            )
        )
        return 1
    finally:
        signal.signal(signal.SIGTERM, previous)
    return (
        0
        if result.get("mechanics_verification") is not None
        or result.get("installed_admission") is not None
        else 1
    )


if __name__ == "__main__":
    sys.exit(main())
