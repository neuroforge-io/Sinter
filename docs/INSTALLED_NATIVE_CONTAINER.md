# Owned Linux native-entry container

`tools/installed_native_container.py` is the separate host owner for the closed native-entry lifecycle. It supports Linux amd64, the one locally retained Ubuntu 22.04 image below, and fixed commands: a fictional container mechanics probe, the original Git-based installed native-entry producer and its separate archive-source route. It never builds, pulls or publishes an image or installer. Its installed route requires the exact committed source archive and matching same-run DEB/package receipt. No new matching DEB has been executed for this source proposal. The actual source/Git probe found that the retained image lacks Git. The original Git route refuses this image before native invocation. The separate closed archive route verifies source inside the same image without Git and keeps the same installed native criteria.

The owner stages fresh private sibling source, bare Git repository, candidate and output trees below a new 0700 owned root. All three input trees are mounted read-only and pairwise disjoint from writable output. The output root must be outside every supplied input and its ancestors. It uses a fresh empty host client home/Docker configuration, strips host settings and credentials, and mounts no host display, account or private workspace. Git trusts only the exact read-only `/repository` through fixed command environment settings, never a wildcard or host/global configuration. The container uses network `none`, root `0:0`, dropped capabilities, `no-new-privileges`, private namespaces and a 64-process bound. Temporary work remains under the private output mount. A name or wildcard is never used for cleanup after creation returns the full actual ID.

Every Docker command retains complete original stdout/stderr files after process reap, complete byte counts/SHA-256 and bounded original samples. The accepted bundle contains exactly the seven ordered roles image/create/created/start/exited/remove/removed. Actual raw pre-start settings are checked before invocation using the same predicate as final admission. Actual post-reap State requires exact integer PID/exit zero, exact boolean running/OOM/paused/restarting/dead false, exact string error empty, and parsed real UTC timestamps with full nanosecond ordering. No source-declared cleanup or passed boolean substitutes for raw inspection. Successful removal uses non-forced removal and a subsequent exact full-ID absence response. Only the two observed closed CLI grammars `Error: No such object: ID\n` and `error: no such object: ID\n` are recognized; permission, daemon and unrelated query errors refuse admission. Original bytes are preserved.

Failed starts retain their observations. Deadline/interruption cleanup targets only the actual owned ID, attempts termination/wait, then forced removal when necessary; that escalation cannot produce admission. Cleanup errors are retained separately and do not conceal the original producer error. A failed cleanup or unobserved final exit remains a failed/unknown execution.

## Exact existing image and historical build

The currently pinned immutable local mechanics/builder image is:

```
sha256:a6abf8768b5d981009b5fd68c7663ed14f87ade82ba8e5aa9be7f856f9313268
```

The actual published E build used this same image, Ubuntu 22.04, `/opt/qualification-python/bin/python` 3.10.12 and PyInstaller 6.22.2. Its retained raw `build-start.json`, `build-container-inspect.json` and `build-completed.json` bind that historical source `246b91e0ee432cb1f6f6fcd17425f55cd7a4cabe`, actual image, command and output assets. These records establish the existing image/build route; their then-pending qualification fields are historical and cannot qualify a new source. The minimal `tools/qualification-image.Dockerfile` and `tools/clean-qualification-image.Dockerfile` are separate runtime recipes and do not recreate this builder. Missing local image is a refusal; no substitute tag or pull is accepted.

The historical fixed build payload was:

```
/opt/qualification-python/bin/python tools/package_native.py --arch x64 --execution native
```

For the later private DEV prototype, the build owner must freshly stage an exact archive of a full private Git source commit, set `GITHUB_SHA` to that same full commit, use the immutable image with network disabled, retain actual create/inspect/start/exit/remove/absence and streams, and use the fixed payload above. `package_native.py` requires PyInstaller 6.22.2, certifi, the supported account dependencies, Tcl/Tk/native build resources and Linux packaging tools. It retains original licenses, source/core assets and native libraries, and runs its historical package self-tests. None of those historical receipt meanings may be rewritten. The package receipt must pin the actual DEV source/version/DEB/frozen binary. Its Debian control Version must equal the source's actual converted version; `0.5.4rc4.dev0` converts to `0.5.4~rc4~~dev0`. Do not retag the source or reuse the E asset. Build execution is separate from this owner's native-entry admission and from RC4 canonical admission.

## Functional mechanics route

Supply an independently reviewed SHA-256 of the actual owner source file. For local development execution a caller can pin the observed bytes, but that execution pin alone is not independent review or release approval.

```
python -B tools/installed_native_container.py mechanics \
  --owner-sha256 INDEPENDENTLY_REVIEWED_OWNER_SHA256 \
  --output /OWNED_NONSHARED_PARENT/FRESH_MECHANICS_ROOT
```

The command owns a real fresh container lifecycle and only reads fictional fixed input canaries, observes original Ubuntu OS metadata/root PID/network/source, proves installed Sinter paths absent, and writes one fictional output canary. It invokes no Sinter, installer, native UI, browser or provider. Its distinct `sinter-owned-native-entry-mechanics/v1` bundle and `sinter-native-entry-container-mechanics-verified/v1` result cannot substitute for installed evidence. The installed route always owns another fresh same-image mechanics run, rather than trusting caller-supplied prior evidence. Mechanics records actual availability of Git, dpkg, dpkg-deb, dpkg-query, Xvfb and xauth; installed execution refuses any missing tool. The current image has no Git. The Git route requires it and remains unsupported; the archive route derives its remaining tooling requirements from the same actual observations.

## Installed route, pending a matching package

Commit every source/tool byte at the supplied full source identity and execute from an exact Git archive copy. A converted checkout, extra file, source import cache or redirected path is refused. The candidate directory staged by the owner contains only the actual two supplied files. For source version `0.5.4rc4.dev0` the expected filenames are shown here, without implying that those assets exist yet:

```
python -B tools/installed_native_container.py run-archive \
  --owner-sha256 INDEPENDENTLY_REVIEWED_OWNER_SHA256 \
  --repository /EXACT_READ_ONLY_GIT_REPOSITORY \
  --source-commit FULL_PRIVATE_SOURCE_COMMIT \
  --installer /PRIVATE_CANDIDATE/Sinter-0.5.4rc4.dev0-linux-x64.deb \
  --package-receipt /PRIVATE_CANDIDATE/Sinter-0.5.4rc4.dev0-linux-x64-test.json \
  --output /OWNED_NONSHARED_PARENT/FRESH_INSTALLED_ROOT
```

For `run-archive`, the host freshly obtains `committed-source.tar` from its actual bare repository and writes `committed-source.json` with the exact identity/manifest. The inner route has distinct `sinter-installed-native-entry-archive-test/v1` and `sinter-owned-native-entry-archive-container/v1` schemas. It accepts only the fixed archive/origin filenames and source-read Python program, the real full Git revision in the tar metadata, complete matching staged member set/version/tool bytes, and exact original metadata before/after. Absolute/traversal/noncanonical paths, links/special members, duplicates, extras/import caches, unsupported metadata, wrong types/sizes and overlimits refuse. The host validator independently re-archives the actual bare Git repository and compares the staged archive/origin. The archive route adds `source_origin_sha256` to its byte-bound outer artifacts. Caller origin fields cannot replace this actual Git derivation.

The original `run` route and default inner Git argv/schema stay separate and unsupported on this image.

The fixed inner archive command is `python3 -B /source/tools/installed_native_menu.py --source-route archive` with the four admitted `/repository`, source commit, `/candidate` filenames and `/out/native-entry` paths. The native entry invokes its installed binary four times: actual Tk create/save/WM-close/reopen/WM-close and the existing two mapped SIGTERM launches. It byte-binds source/DEB/installed binary and both complete desktop entries, package status plus actual dpkg Version, PID/workspace/preferences, original streams and cleanup. The browser desktop entry is bound but not invoked. The host then runs the closed source validator against actual input files and the outer bundle; exit zero alone or supplied booleans do not establish admission.

Success is bounded to the installed Linux native-entry command. Combined browser/native ownership, recovery, E replacement, canonical RC4 assembly, other platforms and a release require their separate actual closed admissions. The source UI mechanism proof and old matched installers remain separate evidence. Full source requirements are in `INSTALLED_NATIVE_ENTRY_TEST.md`.

## Maintenance and bounded evidence

The owner reuses the existing input/package identity and bounded process-capture helpers. It adds one fixed lifecycle implementation and shares raw image/created/exited predicates with the validator. Full stream sinks are optional, leaving the historical command receipts unchanged by default. The old native smoke receipts, validators and 30 original tests are retained. This avoids a second general Docker framework or arbitrary command API; the remaining complexity comes from binding actual source, process and cleanup observations. The installed route has focused parser/refusal/cleanup coverage but requires its first matching actual DEB execution before its operational behavior can be approved.

The shared public lifecycle interface is `validate_lifecycle(rows, pins, creation_argv, mount_spec=None)`. The trusted caller supplies its reviewed fixed `creation_argv(pins, name)` builder and optionally a fixed tuple `(pin_key, container_destination, writable_bool)` for each mount. Raw evidence never selects this policy. Native defaults remain exactly four mounts. `validate_container_observation(observed, pins, creation_argv, name, id, phase, mount_spec=None)`, `validate_image(raw, pins)` and `validate_removal(removal_row, absence_row, id)` use the same predicates. Another owning producer may reuse a separately reviewed fixed mount map; it cannot enlarge native admission.
