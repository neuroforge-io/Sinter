# Installed native-entry check (development source)

`tools/installed_native_menu.py` is an owning Linux x64 qualification producer. It is separate from the existing `sinter-frozen-native-window-test/v1` launch receipt. The current result uses `sinter-installed-native-entry-test/v2`. Historical native-entry/v1 and `sinter-frozen-native-window-test/v1` receipts retain their original meanings. The new result is not an RC4 release validator and does not complete the requirements-only RC4 policy.

Run it only inside a fresh root disposable container with networking disabled, no Sinter installation or leftover paths, and no inherited display. The container needs Git, dpkg/dpkg-deb/dpkg-query, Python with Tk, libX11, xauth and Xvfb. Its root filesystem must be writable for its owned installation. Never mount a host installation, display socket, home directory or real workspace into this container.

Execute the producer from an **exact candidate Git archive copy**, with a read-only Git repository available for comparison. A checkout that applies Windows batch-file CRLF conversion will deliberately fail the byte comparison; execute the exact archive rather than silently normalizing source. All candidate files, including these tools, the separate semantic validator and the fixed native-entry adapter, must be committed at the supplied full source identity. Every archived regular file must match; additional source files, redirected files and import caches are refused. The same-run package receipt must pin that source, version, installer SHA and frozen CLI binary SHA. A development version is execution evidence only, not release admission.

```sh
python -B /source/tools/installed_native_menu.py \
  --repository /readonly-repository \
  --source-commit FULL_CANDIDATE_COMMIT \
  --installer /candidate/Sinter-VERSION-linux-x64.deb \
  --package-receipt /candidate/Sinter-VERSION-linux-x64-test.json \
  --output /out/new-native-entry-proof
```

The output directory must be new. Receipt creation does not count as success: the producer returns exit 1 unless every workflow and removal check passes. SIGTERM becomes an interruption so owned cleanup runs; it is never a successful result. Interrupted/failed steps retain their observations. The driver does not retry a save, infer consent or invoke an AI action.

## Closed scope

Before installing, the producer compares every archived source file and checks the actual DEB package version and architecture. After installation and again after the native work, it separately queries the actual dpkg database for the complete installed status and Version; the input DEB and diagnostic app version cannot substitute for either query. Both complete desktop-entry byte sequences must equal the current source generator and their unique regular DEB members. The installed executable and both installed entries must then equal those actual package bytes; links, extra comments and parser-equivalent changed entries are refused. Full entry bytes and hashes are retained separately for installed observations.

It invokes the admitted native entry's fixed executable/`app --mode native` argv with an isolated fictional `--directory`. It owns an authenticated, TCP-disabled Xvfb on a vacant display and checks that the display lock identifies the newly started server. A separate bounded Python/Tk driver finds the target's client window and binds its actual X parent to the PID-owned mapped window. It enters a fixed literal Unicode project/source through actual widgets, clicks **Save project locally**, invokes the app's registered window-manager close action, then opens and inspects the same saved work through a separate native process. The installed binary's CLI independently reads the saved document; original source text, revision, source identity, preferences and logical database snapshot must survive. The program never uses a Python runtime hook to save the GUI fixture.

The UI driver uses Tcl list construction for literal arguments and runs within a separately timed subprocess. [Tk documents `send` and its X authorization requirement](https://web.tcl.tk/man/tcl8.6/TkCmd/send.htm). This is a private test display, not a general computer-control interface. Missing/ambiguous widgets, another Tk application, wrong PID/window, unavailable authorization or a stalled UI fail the check; no insecure `xhost` fallback is used.

Next, the existing checker actually invokes the same admitted menu prefix twice, recording fresh argv/PIDs separately from its unchanged v1 receipt. Existing strict stderr, diagnostic version, offline source/preferences and normal repeated SIGTERM checks still apply. Separate V2 observations retain complete stdout byte counts and hashes with bounded original samples for both mapped children and Xvfb, and bind every diagnostic/offline invocation to its actual argv, PID, owned workspace and complete original streams. A stream is final only when the child has been reaped before capture begins, its observed exit still matches afterward, and its owned process group is gone. The unchanged legacy mapped v1 stdout field remains its original short text sample. Nonempty new stdout or incomplete stream observations refuse the native-entry workflow. All four entry invocations must have different PIDs. Complete original preference bytes and typed original rows, SQL, column order and metadata from both workspace and campaigns databases are retained in separate observations before and after the mapped launches, and after each Tk phase. Installed entries, executable size/hash, installer and source are rechecked before completion.

The owner removes only its own attempted install, even on earlier failure. Its removal command, package state and `lexists` checks for both entries and the executable are required. A query error cannot masquerade as package absence. Cleanup failures cannot produce a pass. Separately reaped, fixed filesystem probes retain the original path/absence output for both private workspaces, Xvfb socket/lock/authorization, and installed executable/entries; asserted cleanup flags cannot substitute for these probes. Configuration-only package state is recorded honestly; removal is not described as purging every system file.

## Limits and remaining integration

This proves the invoked command, not a physical menu click. The deliberately small native UI journey does not establish all native editing, browser opening/ownership, unsaved-close decisions, pending-request drain, provider behavior, an upgrade, customer desktops or another platform. The browser-menu producer remains separate.

The private proposal's tests use synthetic package streams and process seams. Its actual Xvfb experiment uses the **source** app and proves only the UI driver's create/save/reopen/quit and target refusal mechanics. No matching candidate has been installed by the author. The published E/RC3 DEB lacks the required entry pair and is correctly refused; its historical proof remains unchanged.

Before installed admission, a separate reviewed outer owner must run this exact committed tool against a matching same-run actual DEB in the named disposable image and supply the raw image/container lifecycle bundle described below. The separate functional owner is described in `INSTALLED_NATIVE_CONTAINER.md`; its actual mechanics run is separate evidence. No matching installed execution is supplied by this precursor. Synthetic positive controls exercise semantic parsing; they are not installed receipts. The RC4 canonical assembly and full installed native/browser-owner contract still need their separate closed admissions. Do not manufacture a passing receipt or attach this source-only experiment to a published installer.


## Separate closed semantic admission

`tools/installed_native_entry_contract.py` reads exact inputs and raw observations without installing or launching Sinter. It independently compares the executing archive to the full committed source, reads the actual DEB control/payload and the package receipt, and derives both entries, executable size/hash and Debian version. It accepts only native-entry/v2 and its separate observations; it does not promote old matched receipts or infer browser entry invocation.

The validator checks the complete fixed command sequence, two raw dpkg version/status responses, diagnostic output, two source-bound driver responses, actual native prefixes and four distinct target PIDs with their owned mapped windows. It compares literal source text and typed original database rows, preserves exact preferences and explicit offline selection, requires quiet complete target/display streams and corroborates cleanup using raw filesystem probes. Every required raw response is checked; supplied `passed` booleans are never sufficient by themselves.

A separate outer owner is necessary because the inner container cannot authoritatively inspect its host-selected image, mounts, namespaces, final exit or removal. That owner must be independently reviewed and pinned by source SHA; the validator reads its actual source file and requires the caller's reviewed hash. This pin is a trust input, not a self-declared field. The separate fixed owner is `tools/installed_native_container.py`. Installed admission remains closed until it runs this source against a matching actual same-run package; its fictional mechanics receipt cannot substitute.

The outer `sinter-owned-native-entry-container/v1` bundle has exactly `schema`, `owner_sha256`, `artifacts` and `commands`. `artifacts` must bind `inner_receipt_sha256`, `source_archive_sha256`, `installer_sha256` and `package_receipt_sha256` to the actual supplied files. `commands` must contain the seven ordered roles **image, create, created, start, exited, remove, removed**. Each row has exactly `role`, actual `argv`, integer `exit_code`, original `stdout`/`stderr` stream records and `reaped`. Each stream record has `text`, bounded original `base64` sample, complete `bytes`, complete `sha256` and exact `truncated`; required original inspect responses must fit the complete sample. The owner must capture streams after command reap and separately inspect actual container exit before treating start output as final.

The required owner uses the exact create invocation returned by `outer_argv` in the validator: a fresh `sinter-native-entry-` name with 12 lower-case alphanumeric suffix characters, immutable Linux amd64 image, network `none`, root `0:0`, all capabilities dropped, `no-new-privileges`, 64-process bound, private namespaces and writable disposable root. Exactly four private paths mount: source, Git repository and the two-file candidate directory read-only; output writable. Every mount must live below the independently supplied owned root, and the four mounted trees must be pairwise distinct and disjoint so writable output cannot expose read-only inputs through another path. There is no inherited host display, credentials, extra device, port or mount, and no image entrypoint that could replace the owner. Output is `/out/native-entry`; temporary work stays under `/out`.

Raw `docker image inspect`, `create`, pre-run `inspect`, `start -a`, post-reap `inspect`, non-forced `rm` and post-removal `inspect` must bind one container ID and one image ID. Start must be quiet and exit zero; post-run inspection must show exact created/exited State types, integer PID/exit zero, boolean no OOM/running/paused/restarting/dead, empty string error, and parsed real UTC timestamps in full nanosecond order. Exact successful removal and one of the two bound original uppercase/lowercase no-such-object CLI grammars are required; arbitrary inspection errors cannot prove removal. The bundle is evidence from the independently pinned owner, not an attestation against a malicious host fabricating Docker output.

Run the validator from the same exact committed archive copy only after that owner supplies its bundle:

```sh
python -B /OWNED_ROOT/source/tools/installed_native_entry_contract.py \
  --receipt /OWNED_ROOT/output/native-entry/installed-native-entry-test.json \
  --outer-bundle /OWNED_ROOT/outer-container.json \
  --outer-owner-file /OWNED_ROOT/outer-owner.py \
  --outer-owner-sha256 INDEPENDENTLY_REVIEWED_OWNER_SHA256 \
  --outer-output /OWNED_ROOT/output --owned-root /OWNED_ROOT \
  --repository /OWNED_ROOT/repository --source-commit FULL_CANDIDATE_COMMIT \
  --installer /OWNED_ROOT/candidate/Sinter-VERSION-linux-x64.deb \
  --package-receipt /OWNED_ROOT/candidate/Sinter-VERSION-linux-x64-test.json \
  --image-id sha256:EXACT_REVIEWED_IMAGE_ID
```

A successful admission is bounded to the installed Linux native-entry command and reports the actual bound identities. It does not admit combined browser-menu work, full native owner handoff, RC4 canonical assembly, replacement, Darwin/Windows or a release. The first real same-run candidate execution remains outstanding.


The separate archive route uses `--source-route archive` and the distinct inner `sinter-installed-native-entry-archive-test/v1` schema. Its outer owner stages the actual full-commit archive and manifest from a fresh real bare Git repository; inner checks accept only `committed-source.tar`, `committed-source.json`, the fixed original read program and complete matching source members/revision/version/producer bytes. Host admission independently re-archives the real bare repository. Archive origin/source checks supplement the same four native PIDs, source/DEB/entries/binary, preferences/workspaces, diagnostics and cleanup criteria above. The original Git route/schema stays unchanged and is explicitly unsupported in the retained image without Git. See `INSTALLED_NATIVE_CONTAINER.md` for the executable route and evidence limits.
