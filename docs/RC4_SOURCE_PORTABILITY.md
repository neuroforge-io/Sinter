# RC4 source portability and release status — 2 October

Sinter remains a local-first workbench for one trusted user. The new source is
still `0.5.4rc4.dev0`; no new installer is admitted by these source checks. The
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
The unchanged kernel observations and timeout restoration are retained. Two original Windows batch-launcher timeouts have
no proven cause and remain failures; their five-second limit is unchanged.

A new exact-source hosted run must pass. A final version and source commit then
need a fresh native build, fictional offline installed workflow, interrupted
request recovery, native handoff, four-prior upgrade/replacement, cold install,
notices and asset checks, and independent release authorization. The packaging
preflight found the retained build image and all four prior installer/source
identities; it did not build or qualify an installer.

No new customer platform passed, funding was secured or quality score reached
10 because of this source correction.
