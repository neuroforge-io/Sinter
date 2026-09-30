"""Bind a lightweight release tag to the reviewed commit without moving any tag."""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


def _api(repository: str, method: str, endpoint: str, payload: dict | None = None):
    command = [
        "gh",
        "api",
        "--hostname",
        "github.com",
        "--include",
        "--method",
        method,
        f"repos/{repository}/git/{endpoint}",
    ]
    if payload is not None:
        command += ["--input", "-"]
    try:
        result = subprocess.run(
            command,
            input=json.dumps(payload) if payload else None,
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ValueError(
            "GitHub tag request could not complete; no publication is allowed."
        ) from exc
    headers, separator, body = result.stdout.replace("\r\n", "\n").partition("\n\n")
    status = re.match(r"HTTP/[\d.]+\s+(\d{3})\b", headers)
    if not status or not separator:
        raise ValueError(
            "GitHub tag request returned no HTTP status; no publication is allowed."
        )
    code = int(status.group(1))
    if result.returncode and code < 400:
        raise ValueError("GitHub tag request failed; no publication is allowed.")
    try:
        value = json.loads(body)
    except (ValueError, TypeError) as exc:
        raise ValueError(
            "GitHub tag request returned invalid JSON; no publication is allowed."
        ) from exc
    return code, value


def _require_identity(value: object, tag: str, commit: str) -> None:
    if (
        not isinstance(value, dict)
        or value.get("ref") != f"refs/tags/{tag}"
        or not isinstance(value.get("object"), dict)
        or value["object"].get("type") != "commit"
        or value["object"].get("sha") != commit
    ):
        raise ValueError(
            "Release tag does not directly identify the reviewed commit. "
            "Conflicting or annotated tags are never replaced."
        )


def _candidate_identity(manifest: Path, repository: str, tag: str, commit: str) -> None:
    """Require rechecked qualified assets before accepting a scoped rc tag."""
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from tools.candidate_release import verify_plan

    plan = verify_plan(manifest)
    if (plan["repository"], plan["tag"], plan["source_commit"]) != (
        repository,
        tag,
        commit,
    ):
        raise ValueError(
            "The verified candidate manifest names another release identity."
        )


def ensure_release_tag(
    repository: str, tag: str, commit: str, candidate_manifest: Path | None = None
) -> None:
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Use an explicit owner/repository.")
    if not re.fullmatch(r"v\d+\.\d+\.\d+(?:rc[1-9]\d*)?", tag):
        raise ValueError("Use a stable version tag or an explicitly qualified rc tag.")
    if not re.fullmatch(r"[0-9a-f]{40}", commit):
        raise ValueError("Use the full lowercase 40-character reviewed commit.")
    if "rc" in tag:
        if candidate_manifest is None:
            raise ValueError(
                "An rc tag requires an exact verified scoped candidate manifest."
            )
        _candidate_identity(candidate_manifest, repository, tag, commit)
    elif candidate_manifest is not None:
        raise ValueError(
            "A scoped candidate manifest cannot authorise a stable release tag."
        )
    endpoint = f"ref/tags/{tag}"
    status, value = _api(repository, "GET", endpoint)
    if status == 200:
        _require_identity(value, tag, commit)
        return
    if status != 404:
        raise ValueError(
            f"GitHub returned HTTP {status} while checking the release tag."
        )
    # Creating a ref is atomic: an existing ref cannot be overwritten by POST.
    status, value = _api(
        repository, "POST", "refs", {"ref": f"refs/tags/{tag}", "sha": commit}
    )
    if status == 201:
        _require_identity(value, tag, commit)
        return
    if status == 422:
        # Another attempt may have created it after our GET. Only the exact
        # reviewed commit makes this a safe retry; never update or force a ref.
        status, value = _api(repository, "GET", endpoint)
        if status == 200:
            _require_identity(value, tag, commit)
            return
    raise ValueError(f"GitHub returned HTTP {status}; the release tag is not verified.")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="GitHub owner/repository.")
    parser.add_argument("--tag", required=True, help="Version tag to verify or create.")
    parser.add_argument(
        "--commit", required=True, help="Full commit tested by this workflow."
    )
    parser.add_argument(
        "--candidate-manifest",
        type=Path,
        help="Required verified scoped asset manifest for an rc tag.",
    )
    args = parser.parse_args(argv)
    try:
        ensure_release_tag(
            args.repository, args.tag, args.commit, args.candidate_manifest
        )
    except (
        OSError,
        ValueError,
        KeyError,
        TypeError,
        subprocess.SubprocessError,
        zipfile.BadZipFile,
        tarfile.TarError,
    ) as exc:
        parser.exit(1, f"{parser.prog}: {exc}\n")
    print(f"Verified {args.tag} at {args.commit}.")


if __name__ == "__main__":
    main()
