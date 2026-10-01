# Local recovery source rehearsal

`tools/rc4_recovery_source.py` is a separate Linux source rehearsal for a future
RC4 recovery gate. It runs a reviewed, complete source snapshot with fictional
local data. It does not install a package, admit any candidate version, or produce
an installed recovery receipt. The existing RC3 `sinter-installed-recovery/v1`
contract, defaults, artifact roles, prior maps and historical receipts are unchanged.

The source result uses the closed `sinter-rc4-local-recovery-source/v1` schema.
Its `candidate_admitted`, `installed_tested` and `release_qualified` fields must all
be false, including when `source_rehearsal_passed` is true. An observed
`0.5.4rc4.dev0` source version is not a release admission.

## What actually runs

Six separate source desktop processes run in explicit browser mode. The harness
captures the operating-system opener, pauses background watch polling, blocks
provider calls, and forwards only its owned loopback listener to a headless browser.
Those test controls are disclosed in every child receipt. Nothing opens the user's
physical application or visible browser. Python and Chromium must already exist;
the producer does not install dependencies or contact an external service.

The first four runs exercise the complete ten-phase campaign-v1 sequence: held
work, a cold reopen, a closed route, resumed work within the closed route, reactivated
route, stopped-process clipboard/manual recovery, and separate restored copies.
The whole backup text is retained, including UTF-16 selection bounds. Actual CSV
and calendar bytes retain unknown/unassigned owners, proposed rather than confirmed
dates, and held/historical scope exclusions. These UI steps and pure semantic helpers
are reused from the historical producer; the old installed receipt is never relabelled.

Two more runs exercise a phone conflict and uncertain acknowledgements. Another
window really saves a correction; the stale window must keep its local input and a
complete backup. A subsequent save really commits, but its successful reply is
replaced with a fictional 503. There must be one request and no automatic replay
during the observed 250 ms quiet period. Dirty in-page Quit → Keep working sends no
quit request. An explicit subsequent Quit really stops the source process, while its
reply is replaced with a 503. The loaded browser must retain full unsaved input and
export a complete local backup. A fresh process then reopens the actual committed
save and verifies the separate originals before a confirmed clean Quit.

The older human “met” mark remains literal while the browser explicitly warns that
the registered source and excerpt dates differ. This does not verify the source or
turn a user mark into an eligibility decision.

A seeded casebook, report, exact source excerpt, applied human wording and disabled
watch remain protected raw SQLite records throughout. Explicit fictional provider,
model, personal preferences and original preference-file bytes must be conserved.
Live-file `user_version`, `application_id`, `encoding`, `page_size`, table SQL and
column structure are observed before any cold Runtime reopen. Campaign rows change
only through the admitted phases and separate uncertain control; the final raw rows
must contain exactly the three recovery originals/copies plus that control.

Every child exit, closed-port observation, complete stdout/stderr byte count/hash,
reversible bounded diagnostic sample and full raw stream file is retained. Only the
exact browser notice extracted from the pinned desktop source is accepted on stderr.
Cleanup/observation faults retain diagnostics and a failed result, never a source
pass. Output is fresh, outside the source, and contains a closed 47-artifact inventory.

## Run it

Use an extracted or frozen source directory, without Git metadata, bytecode caches
or other unlisted files. Its external manifest must contain `base_commit` (40 lower
hex characters) and `files` (every regular relative file path mapped to its SHA-256).
Review and record that manifest's SHA-256 separately. The producer checks the complete
inventory before browser tooling or any output and again after cleanup. A linked,
changed or missing source file is refused.

```sh
TMPDIR=/your/owned/short/home-temp PYTHONDONTWRITEBYTECODE=1 \
  /your/existing/python -B tools/rc4_recovery_source.py \
  --source-manifest /your/reviewed/source-freeze.json \
  --source-manifest-sha256 YOUR_REVIEWED_MANIFEST_SHA256 \
  --source-commit YOUR_REVIEWED_BASE_COMMIT \
  --output /your/owned/fresh-proof \
  --chromium /your/existing/chromium
```

Run from the frozen source. The optional browser path also accepts `SINTER_CHROMIUM`
or the existing Playwright browser configuration. The Python environment needs the
repository browser extra already present. `--help` works without that extra. Python
optimisation is refused because the reused browser steps use assertions. Linux is
the only supported rehearsal platform; a short owned home temporary directory avoids
Unix-socket pathname limits. No actual Windows or macOS recovery is claimed.

Success exits 0 only after artifact semantics, source conservation and cleanup pass.
Failures exit nonzero and retain a false receipt and available failure/stream evidence.
A failure is not a passing receipt and must not be copied into a release evidence role.
Independent review can call `validate_rehearsal` with the externally pinned source
map, base commit and manifest hash. The generated result is local producer evidence,
not a signature or independent attestation.

## Remaining gates

This is a functional campaign-v1 subset. It does not close the separate RC4 installed
recovery requirement. Scoped casebook-v2 complete clipboard/manual recovery, scoped
capability-present/wrong/duplicate/missing-header paths, unsupported readers, and rich
casebook source/history recovery across stopped processes remain required. It preserves
a seeded v1 casebook/report rather than rehearsing their editor recovery here.

Actual frozen-binary/package execution, notice and source/archive identity, installed
native-owner handoff/drain/timeout controls, menu/native-entry bytes and invocation,
removal, exact published RC3 replacement without prior uninstall, and the closed RC4
canonical gate remain separate missing proof roles. No old source rehearsal, mapped
window test, or published receipt can substitute for those future executions. Release
policy still refuses RC4 until its separately reviewed closed gates exist and run.
