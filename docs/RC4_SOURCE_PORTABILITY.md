# RC4 source portability and release status — 2 October

Sinter remains a local-first workbench for one trusted user. The new source is
the `0.5.4rc4` candidate source; no new installer is admitted by source checks. The
published RC3 preview and its original assets stay unchanged.

## Original hosted outcomes

- `f73cf45b5f14e357f4a2aede4b554c56d495478e`, Quality run
  `36962603645`, attempt 1: all 12 jobs succeeded. Each original Python phase
  reported 4,607 unique cases, retaining platform skips. Its five Linux native
  GUI source checks were a separate phase. This is a baseline source result.
- `3132ad91c89680e98ab5c8ac739c23b696586f7a`, Quality run
  `36964758587`, attempt 1: all six Python jobs failed. Linux and macOS each had
  five failures per Python version; Windows 3.10 had 29 and Windows 3.13 had 49.
  All original failing job logs and uploaded ZIP/XML files are retained.
  Chromium workflows, RKC interoperability and the three speech jobs succeeded;
  the final verified-source job was skipped because its prerequisites failed.
- Earlier run `36959550809` for `3ab6a2` has separate observations: attempt 1
  was cancelled; an externally started attempt 2 failed. Neither result replaces
  the other. The original macOS filename refusals and Windows Node timeout remain
  historical evidence.
- Successful DEV publish runs are deliberate no-ops. They do not produce or
  publish a candidate.

The original capture manifest has 191 regular references and SHA-256
`c2436f643cee85df468337ce2e1a7accf02b6df7078036770704207e6a8a26f3`.
It preserves the original arithmetic note and its separate correction.

## Workflow source corrections

Valid fictional input paths now use the host's absolute-path syntax. The two
inert Linux controller fault controls explicitly provide their fictional UID/GID
metadata. Actual process-group and preparation ownership controls require the
POSIX resources they exercise; absent resources are reported as skips.

Preparation tests use a fresh, private, short temporary root owned by the actual
non-root user. They retain the production ownership, permissions and 55-byte
path guards, rather than assuming a runner UID or home length. Their existing
first-error and complete-diagnostic assertions remain active.

The CLI diagnostic test uses an actual byte filename when admitted by the
filesystem. Only EILSEQ selects the Unicode alternative; permission and capacity
errors still propagate. Both output targets are owned directories, so actual
primary and fallback refusal is reproducible on every filesystem. Surrogate
content still round-trips exactly even where the filesystem cannot create that
byte filename. A successful fallback is never relabelled as failed publication.

The old RC3 notes test names RC5 for its unsupported-version negative. RC4 now
has an explicit separate release policy; the original RC3 admission and stage
checks remain intact.

The private two-file workflow proposal passed 179 local source checks in
21.72 seconds with no skips. An independent exact replay and additional controls passed 199 distinct
source cases, including all 179 proposal cases. The reviewer conserved every
original assertion and all production bytes. The joined replay result is recorded in the quality review after execution.
These are Linux source observations, not hosted
Windows/macOS or installed-app evidence.

## Joined source replay

The combined 16-file source replay passed 1,583 unique cases without failures,
errors or skips in 80.17 seconds. Its three Pytest diagnostic-property/JUnit
format warnings remain in the complete raw output and XML. Correctness/import
lint, formatting, Python 3.10 grammar and the public-boundary check passed.
These results do not qualify installed or Windows/macOS operation.

## Remaining release gates

The Windows manifest identity correction passed 299 relevant source checks
and six independent file/race/cleanup controls. Official pinned CPython 3.13.15
implementation explains a Windows cross-API timestamp mismatch: path and
descriptor observations can use different meanings for ctime. The original
runner timestamp values were not captured, so that cause remains an inference.
The reader binds shared device/inode/size/mtime and available birthtime, while
comparing each channel’s full metadata before and after reading. POSIX retains
its full cross-channel comparison. Pinned bytes, size limits, JSON rules and
original release authorization remain required.
The socket fixture correction has passed independent replay: it reproduces the
original selector call-shape refusal, establishes actual unread TCP backpressure
and preserves the original cancellation and 0.25-second operation limits.
The unchanged kernel observations and timeout restoration are retained. The
two earlier Windows batch-launcher failures retain their original outcome and
unproven cause; their five-second limit is unchanged. The later exact079 run
passed those cases, as recorded below.

The exact final candidate source must pass its hosted run before building. It
then needs a fresh native build, fictional offline installed workflow, interrupted
request recovery, native handoff, four-prior upgrade/replacement, cold install,
notices and asset checks, and independent release authorization. The packaging
preflight found the retained build image and all four prior installer/source
identities; it did not build or qualify an installer.

No new customer platform passed, funding was secured or quality score reached
10 because of this source correction.


## Follow-up hosted observation

Exact `079263662b079051aeb2fedd361dfd90e1cc3636`, Quality run
`36969962677`, attempt 1, ended FAILURE. All six Python phases collected
4,996 cases. Linux passed 4,986 with 10 skips per version; macOS passed 4,650
with 346 skips per version. Each Windows phase passed 4,423 with 572 skips
and one failure: the cancellation fixture did not establish its pending event
within two seconds. Its failed-run byte counts, buffers and socket modes were
not recorded and remain unknown. This does not establish a production relay bug.
All six phases retain six actual warnings.

The 23 exact earlier Windows manifest failures now pass. The two earlier
Windows 3.10 batch-launcher cases also pass on this source, without proving the
old timeout cause. Of 66 historical workflow failure invocations, 56 now pass
and ten remain explicit POSIX-resource skips on Windows. The separate Linux
native GUI phase passed five source checks. Chromium, RKC and all speech jobs
succeeded; the dependent verified-source job was skipped. The DEV publishing
run was an actual no-op with no assets. Complete original logs, ZIPs and XMLs
are retained in the 120-reference capture, handoff SHA-256
`2a4017b3b31198ac6a47190b2216c267704678628b8f9d042c434605aefdbc7c`.

The independently accepted follow-up changes only the cancellation source test.
It records an exact positive original payload prefix separately from bounded
fixture prefill. Prefill cannot establish pending: a subsequent actual production
empty write-select or would-block result must do so while the original send is
active and uncancelled. Zero additional fixture bytes require that explicit
active context; an ordinary fresh fill still requires positive new bytes.
The one 20-second operation budget, two-second pending/cancellation limits and
0.25-second timeout control remain unchanged.

An adversarial cleanup control held the first proposal: a later socket-close
error could hide the original setup error. The fresh correction attempts every
owned socket close in LIFO order, preserves the first exception and retains all
later close failures and finally diagnostics. The original HOLD and successful
source replays are preserved as separate historical observations. The corrected
module passed 48 cases with no skips; independent supported fault and invalid
context controls also passed. Those are Linux source observations, with
explicitly injected faults, rather than a claim about the unknown original
Windows socket state.

The source review handoff is
`c3c781beb3debf06db02dc7d0344e66e0710d765e0e1336afe03c1e55f265ec9`.
Its separate mode erratum distinguishes Git archive header permissions from
physical extracted permissions and canonical Git executable classes. All 479
unowned source files retain their bytes and canonical Git modes; no equality of
raw archive and physical permissions is claimed. Local replay does not replace
the next exact-source hosted run or installed qualification.


## Final candidate source replay

The final composed 17-file Linux source replay passed 1,600 unique cases with
no failures, errors or skips in 124.00 seconds wall time. Its six actual
Pytest diagnostic-property/JUnit warnings are retained in the original stdout
and XML. Required full-tree CI correctness lint, changed-Python F/I lint,
formatting, Python 3.10 grammar and the public-boundary check passed. The broader
full-tree F/I check failed with 42 diagnostics; exact comparison found the same
42 diagnostic signatures on unchanged079. That failure and comparison are
retained, with no broader-lint PASS claim or unrelated source edits.

The cancellation correction has separate independent source acceptance,
including first-error preservation, all later cleanup errors, invalid-context
refusals and an actual active zero-additional-fill control. Production code and
operation limits remain unchanged. The earlier held proposal and all successful
historical replays stay intact. Natural original Windows socket state remains
unknown. These overlapping source observations do not qualify installed
behavior, raise the product score or replace final-source hosted checks.


### Actual installed workflow correction, 2 October

The first exact791 installed browser journey quit normally after six completed
checks, but its qualification owner rejected the product's startup banner.
A separate cleanup field error is retained alongside that first failure. The
source correction admits only the exact banner bound to the actual local URL
and listener, records the fixed temporary directory before collector startup,
and permits narrow cleanup after a fully observed failed collector without
turning it into a passing workflow. Existing stream, ownership and inventory
guards remain. The original partial run does not establish reopen, restore or
Word export. Its package is held; new exact-source hosted and full installed
qualification are required. See the dated quality-review record for scope.
