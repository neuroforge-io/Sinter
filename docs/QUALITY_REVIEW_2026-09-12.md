# Sinter user-testing closeout — 12 September 2026

## 2 October RC4 source portability follow-up

Actual main3fe344a and funding review7dd1272 each had the same seven Windows
failures. Six arose from a host-tool fault fixture comparing Windows Path text
with a POSIX slash string; native Path equality retains the actual path check
and the existing first-error/complete-observation assertions.

The seventh actual TCP test recorded two successful shutdown calls while its
owned worker remained blocked in a20-second recv. The separate RC4 HostRelay
now wraps client reads with a0.1-second cancellation poll while reusing the
unchanged legacy RelayRequest parser and per-read timeout. Its close event
precedes shutdown, and setup/finish retain the real socket. Counters still leave
only in the actual worker finally block. No pinned legacy transport, installed
Linux admission guard, framing rule or browser policy is changed.

Regressions retain the real Windows/Linux idle connection and add a no-wakeup
shutdown fault seam. They require bounded cleanup, zero idle errors, listener
closure and repeat close. Real consumed partial header/body requests must still
increment the error count and release ownership. Raw-byte/deadline/read-error
and existing surviving-worker diagnostic controls remain. Queued bytes that
were never consumed are cancelled rather than drained into a new request after
stop. These source checks do not qualify installed Windows/macOS operation.

The laptop resource guard withheld the focused test command; no child test ran.
Execution evidence must come from the existing approved hosted CI before merge.

The ten session findings were reproduced or traced to their implementation, fixed
where appropriate, and tested with deterministic regressions and fictional live
inputs. The endpoint-bound review identity in F7 remains an intentional protection.
These are source improvements; they do not claim that a new installer release has
been published.

**Historical checkpoint.** The counts, live outputs and scores below describe the
September 12 review, not the September 30 candidate or the currently deployed
native model. Current profile boundaries, offline and installed qualification
are recorded in [published 0.5.4rc1 status](PREVIEW_0.5.4rc1.md) and
[the published 0.5.4rc2 preview](PREVIEW_0.5.4rc2.md). Native ERAIS supports
1–128 output tokens and short buffered questions; the earlier 32–2,048 range and
long-recipe successes apply to legacy contracts. No historical score substitutes
for current acceptance.

## Finding disposition

| Finding | Result | Main regression evidence |
| --- | --- | --- |
| F1: no-argument CLI starts a server | All CLI entry points print help and exit. Explicit serve and desktop launchers still open Sinter. | `test_review_recovery.py`: piped subprocess entry points and explicit serve |
| F2: research template truncates | Larger bounded research budgets, concise prompts, shared completion checks, no fabricated streaming finish status. Incomplete output is recoverable in CLI, JSON, streams and jobs; dependent steps stop. | `test_template_reliability.py`, `test_user_findings.py`, live streamed/nonstreamed research |
| F3: recipes lose context | Every drafting/checking step carries original source fields and prior work, with explicit system/task instructions and bounded history. | All eight recipe prompt contracts; live enquiry and consultation in both modes |
| F4: research produces a blank letter | Dedicated Research workflow produces source highlights, focus questions, citations, coverage and gaps. Generative research remains a separate labelled template. | `test_user_findings.py`; research browser/save/export round-trip |
| F5: wrong resume output path | Bounded local discovery finds a unique matching receipt; `--checkpoint` resolves ambiguity. Errors explain recovery. | `test_review_recovery.py`; genuine saved answer recovered to another output without replay |
| F6: useful prose stays partial | Accept grounded line-referenced findings and substantial source phrases while rejecting refusals and unsupported generic answers. Reassess existing partials locally; explain remaining follow-up/manual work. | Adversarial refusal, negated-clean, prose, follow-up cap and uncertain-transition regressions |
| F7: endpoint changes invalidate resume | Preserved and documented. Source, questions, language and API identity must agree; uncertain requests require explicit retry. | Identity and uncertain-retry regressions |
| F8: opaque low-token API failures | Reject unsupported token and public-provider input budgets locally with actionable messages. Settings reflect the public 32–2,048 range; custom providers retain their broader range. | Boundary tests, 22 fixtures compared with the site's public request validator, live 32-token Unicode request |
| F9: atlas consent fails asynchronously | Consent is checked before admitting a job, with the execution check retained. Missing/invalid consent returns HTTP 400 and creates no job. | HTTP admission regression; no model call |
| F10: developer tools crash without arguments/dependencies | Shared optional-browser setup and proper usage/help. Missing setup stays nonzero; release and integration checks remain strict. | `test_tooling_cli.py`, release-manifest tests, real browser/RKC checks |

Other session notes addressed: correct fictional banners for each workflow,
human-readable `source_title` selection for grant criteria, and meaningful public
API limit validation. No changes were made to the sibling NeuroForge site; it was
pulled repeatedly to verify its current API contract.

## Adversarial improvement cycles

The independent critic tested counterexamples and inspected screenshots rather
than accepting passing status codes alone. Its first pass found additional defects:

- Source-request refusals could pass the review completion gate, while a useful
  single-subject finding failed it. Negated "no issues" language was ambiguous.
- An uncertain follow-up could lose its previous commentary and retry counter.
- Reports saved inside a reviewed folder could contaminate later inputs; output
  could also overwrite the selected source file.
- A late search failure could discard completed template steps.
- Research question citations could refer to an excerpt absent from the exported
  document. Generic question words could select unrelated wording.
- Meeting passage counts used an empty excerpts array instead of transcript
  segments. Escape in the finder search field cleared text without closing it.
- RKC receipts named a pinned revision without identifying the tested binary.

Each was corrected and independently rechecked or covered by a browser regression.
The RKC receipt now records the actual executable digest and available embedded
version/revision, with an explicit comparison to the CI pin.

Live output reading also caught an irrelevant location association in generative
research and a recipe self-check that repeated the questions. Stronger scope/task
instructions corrected those tested examples. This does not establish universal
model reliability or make a model self-check independent verification.

## Validation

- **450 Python tests passed locally**, plus the repository's fatal Ruff and
  whitespace gates, public-boundary check and offline source/provenance self-audit.
- Core, studio, desktop, casebook and public-landing browser suites passed. The new
  quality suite passes nine scenarios with 32 screenshots, covering finder
  keyboard/focus, research round-trips, settings, meeting statistics,
  complete/partial templates, failed-job recovery and safe Markdown rendering.
- Responsive checks cover 320px and 390px, both themes and both reading sizes.
  All measured document widths fit their viewport. Sampled text-token contrast
  is at least 5.911:1 in light mode and 7.996:1 in dark mode; this is not a full
  accessibility certification.
- Browser regression fixtures made no external browser requests and reported no
  page or console errors. The primary agent separately used the requested in-app
  Browser for keyboard discovery, research generation, source jumps, local
  save/reopen, mobile comparison and a real enquiry-template run.
- Six final live template runs (research, enquiry and consultation; streamed and
  nonstreamed) completed all 18 steps. Paired output text matched. A separate live
  Unicode request at 32 tokens completed, and the primary agent's browser enquiry
  completed all three steps with source context retained.
- The installed RKC 0.4.0 completed compilation and real HTTP context retrieval:
  five returned items, snapshot/citation binding checked, zero model calls. Its
  embedded revision differs from the CI pin, and the receipt records that fact.
- Wheel, source distribution and portable zipapp builds passed. The installed
  command is linked to this checkout; an already-running Sinter process must be
  restarted to load Python changes.

Local evidence is retained in `browser-artifacts/quality-summary.json`,
`rkc-artifacts/compatibility.json`, `self-audit-artifacts/receipt.json` and the
ignored build outputs. CI runs separately exercise Python 3.10/3.13 on Linux,
macOS and Windows, plus browser, speech and pinned RKC integration. The Windows
fixture failure found during this work was fixed by respecting native home-path
resolution; the consent test was retained.

## Assessment

| Dimension | Independent critic score | Basis |
| --- | --- | --- |
| User experience | 8/10 | Discoverable tools, safe recovery, clear failure states and source navigation |
| Functionality | 8/10 | Findings closed with adversarial counterexamples, real API checks and regressions |
| Aesthetics | 8/10 | Coherent dark/light layout, readable task hierarchy and responsive reports |

These are engineering assessments, not representative end-user research. No 10/10
claim is made. Remaining limits include lexical rather than semantic retrieval,
model adherence variability, temporary in-process job retention, and long evidence
documents. Partial reviews now return exit 3, failed or uncertain provider outcomes
return 1, and invalid CLI usage retains exit 2, so automation can separate follow-up
from failure. Source links and hashes establish provenance, not truth; official
decisions and communications stay with the user.

## 30 September source-workflow reassessment

The September 12 scores above remain historical. Actual operator use of long
campaigns and source-only handovers found further defects; those scores do not
establish current whole-product acceptance or the user's requested 10/10 bar.

The following changes follow the frozen Linux-only 0.5.4rc2 release at
`256d38fa4b61a4d548472ce5abfd0bf513789090`. They are development source changes,
not changes to its installers or evidence of another installed platform passing:

- A large real campaign could be refused because validation counted normalized
  strings more than once. Shared capacity checks now count each value once and
  warn before the unchanged admission limits; rejected input can still be backed
  up and deliberately reduced.
- An explicit handover option preserves all selected passages in a portable
  appendix. It does not include every unselected original or turn related wording
  into answers. Bounded Word grouping keeps short source captions and reference
  keys beside the related material; narrow editor tracks fit the viewport.
- Explicit visible source-selection buttons replace unreliable datalist
  interaction. Searching does not change a link. Ambiguous identities are
  excluded, historical snapshots remain identifiable, and linking a different
  source retires its earlier assessment until a person reassesses it.
- Pending draft edits now block copy, download, print, local save and campaign
  correspondence logging until explicitly applied or cancelled. Refusal happens
  before logging or changing a saved campaign revision.
- Funding ceilings carry an explicit denomination. Legacy AUD meanings are
  retained; new entries start unconfirmed. Non-AUD ceilings are never compared
  numerically with AUD project costs, and no conversion or award is inferred.
- The native client allows 55 seconds for transport while the qualified service
  edge remains 50 seconds. Mocked delayed delivery exercises completion, bounded
  refusal, cancellation and shorter enclosing deadlines without replay.

Independent reviews found no remaining blocker in those bounded changes.
Focused regression and browser receipts cover identity, partial results, saved
work, revision conflicts, backups, exports and literal Unicode evidence. Before
the native timing follow-up, the full Python suite passed **1,914 tests with five
platform-inapplicable skips**. The timing follow-up independently passed 297
focused native/provider/admission tests. This is source validation, not a claim
that a hosted answer is useful or an installer contains these changes.

A fictional 170,000-code-point portfolio benchmark used 81 sources, 27 products,
12 routes and 10 communications. Its 61 measurements include automation and UI
waits: median save 195 ms across five samples, with a retained 931 ms maximum;
median fresh-context reopen 295 ms across three samples. These small local
samples establish neither a service-level guarantee nor customer-device speed.
They also exposed Save controls far below the active search fields, a usability
gap that timing alone would have missed.

The independently rendered raw nine-page evidence dossier scored **6.5 for user
experience, 7.5 for artifact fidelity and 7 for aesthetics**. Those are scoped
engineering judgments, not product-wide scores, legal or funding conclusions,
or representative customer research. The dossier retained all selected passages
but still needed a concise operator-written decision page and clearer page
boundaries. Long-source fragments and lexical selection remain practical limits.
No 10/10, completed live-assistant task, secured funding or automated-submission
claim follows from these checks.

### Closing the observed save and document-layout gaps

An explicit editor page-boundary control now preserves the surrounding wording
and represents a native Word break and a printed HTML break. It refuses a
non-rendering insertion inside literal material without changing the editor.
Independent checks covered five actual save/reopen/export journeys, Unicode
cursor boundaries and literal nested markers. Normal exports remain byte-for-byte
stable. Actual private operator packs were reviewed separately from the fictional
control fixtures; their evidence and historical generated reports were retained.

The campaign Save and preview controls now stay visible above the long editor.
An initial constrained-height review found covered fields; the corrected layout
passed eight actual browser viewports, including 320-by-400, 320-by-501,
320-by-601 and 651-by-400 windows, with 40 complete-field visibility checks.
Save/reopen and competing-revision refusal preserved the exact fictional
portfolio. Editing clears only an earlier success notice; conflict errors and
pending wording remain available. The scoped control assessment was **8 for user
experience, 8.5 for functionality and 7.5 for aesthetics**. It does not qualify
physical mobile keyboards, an installed package or the whole product.

At the campaign-control checkpoint, the full Python suite passed **1,939 tests with
five platform-inapplicable skips**. The configured fatal Ruff gate, public-boundary
check and deterministic offline self-audit also passed. The actual browser checks
reported no external or model calls. A reusable profiler retained another 61
measurements against the exact original fictional fixture, with ten separate
driver-overhead measurements. Concurrent host work was uncontrolled: this is
repeatable workflow evidence, not an A/B speedup or customer latency guarantee.

The real NeuroForge portfolio was closed, the app stopped and restarted, and a
fresh browser opened its latest saved revision. Its exported backup was byte
identical, retaining 13 routes, 84 sources, 27 products/assets, ten communications
and 19 actions. No credentials, private correspondence or campaign evidence were
added to the public repository or release assets. No hosted model allowance was
used, and no new application or outgoing message was sent by this cycle.

### Browser download handoff and explicit local recovery

Download feedback now reports a request to the browser rather than claiming a
file was saved. Local Blob URLs have a bounded 60-second handoff lifetime and
immediate cleanup on a dispatch exception. A repeated explicit Word click reuses
the exact prepared title and applied wording. Changed titles or wording require
a new local compile; pending or changed input introduced while compilation is in
flight prevents a stale export and retains the editor.

The independent review passed ten source-bound fictional browser journeys and
seven additional adversarial scenarios, including delayed handoff, compile
failure, rapid clicks, conflicting input and isolated reports with identical
titles. Existing export and recovery journeys also passed. The full local Python
suite passed **1,944 tests with five platform-inapplicable skips**, alongside the
configured fatal Ruff and narrow public-boundary checks. These are source tests,
not installed-platform or customer-device qualification.

Separately, the actual in-app browser produced Word and JSON files for three
saved NeuroForge preparation cases. Checks compared retained files, not success
notifications, and preserved the original report fields, source identities and
complete generated handover wording. An explicit unchanged repeat produced an
identical Word file. Earlier in-app attempts had displayed a notification without
a retained file; the successful recheck also followed a fresh app process and
browser tab. The original failure's cause is not established by these observations
or by the deliberately delayed fictional handoff probe. No browser security
setting was changed or bypassed. The scoped download-control judgment was **8 for
user experience, 8.5 for functionality and 7.5 for aesthetics**, not a whole-product
rating. Published preview installers are unchanged.

### Requirement notes survive source changes

An actual operator first entered a requirement's explanation, then linked its
source. The earlier picker erased the note and clarification state. The corrected
picker preserves exact explanatory wording on link, replacement and clear;
met/not-met assessments still reset when the source changes, and earlier quoted
wording is cleared. A visible message explains the recheck. Unknowns and
clarification remain unresolved rather than becoming positive evidence.

Independent qualification passed **117 campaign JavaScript tests, 52 focused
Python checks, six fresh desktop/mobile browser journeys and 2,160 frozen
transitions with 38,232 assertions**. The real campaign's clear/relink exercise
also preserved its note and clarification state. Its revision-46 exported inputs
were byte identical to revision 45. No model request or outgoing message was
needed, and previous snapshots remain available privately.

The current portfolio profiler completed **61 samples** against the exact
fictional baseline (170,000 code points; 208,371 bytes), with ten separate driver
measurements and unchanged source during the run. Median observations were
336.8 ms for fresh open, 275.0 ms for warm open, 210.3 ms for modified save and
392.5 ms for exact reopen. These include browser-driver/scroll/assertion work on
an uncontrolled shared host. They are not customer latency guarantees or an A/B
speedup. The first attempt could not locate its default browser and produced no
samples; it remains a failed setup receipt. The successful run explicitly used
the existing installed Chromium binary. All owned profiling resources closed.

### Complete Word references without a nearly empty final page

The actual Linux Australia operator pack initially used six pages, with only the
last reference mapping on its final page. Bounded paragraph spacing now applies
only to complete generated passage-key records. Its final export uses five pages,
keeps all five complete mappings on page five, and has pixel-identical first four
pages. Fonts, words, identities, Unicode ranges, non-key paragraph XML and other
package members remain exact. The other two real packs retain ten and seven
pages, with their front page on page one and supporting handover on page two.

The independent reviewer found both a nested-quote lookalike and an equal-wording
quote elsewhere that could wrongly admit a mapping. Final admission checks bind
each raw quote to its actual position in the key section. **222 focused Python
checks and 48 additional adversarial probes passed**. The three actual retained
downloads matched the final compiler exactly and passed **473 fidelity/layout
checks**, with visual review of front and reference pages. This is layout
qualification of those local packs, not a quality decision about their sources,
eligibility, IP or funding.

A clean source copy of the preceding pushed checkpoint plus these two reviewed
fixes passed the full Python suite: **1,989 tests with five platform-inapplicable
skips**. The copy's exact source hashes are retained in its local qualification
receipt. Concurrent unfinished provider/readiness edits owned by another active
chat were excluded and retained untouched; a separate mixed-tree run had twelve
failures in its catalogue-response mocks and is not reported as a pass. Fatal
Ruff, whitespace and the narrow public-boundary checks passed. No new installed
preview, hosted model result or whole-product 10/10 follows from this source
checkpoint.

### Held work and recovery without a running server · 1 October

The independent review of three actual operator packs still rated usefulness
**7**, evidence function **7.5** and Word presentation **7.5**. One earlier action
remained current despite a later scope decision. The new explicit **On hold**
status retains its exact task, proposed owner/date and history, excludes it from
current suggestions and calendar exports, and requires explicit resume. Route
and scope checks remain in force. The assistant rejects a held next-action
request before model discovery or generation; other tasks retain labelled history.

Held qualification included **199 focused Python checks, 69 JavaScript checks,
576 frozen cases each in Python and JavaScript with 9,216 assertions each**, and
**1,152 exact comparisons with earlier open/done documents**. Fresh desktop and
mobile UI journeys confirmed the warning that published 0.5.4rc2 cannot open
records containing held actions. Its refusal leaves the record unchanged; this
is a source compatibility probe, not an installed downgrade test. Do not turn a
held action into completed work merely to satisfy an older version.

Another actual browser attempt retained unsaved inputs after its server stopped
but produced no backup file. The original download failure's cause remains
unproven. The new local backup-text controls provide an independent recovery
path: complete working-copy JSON, explicit clipboard copying, manual selection
and refresh that stays available when clipboard access stalls. They neither save
a campaign nor create a file. Oversized text is preserved without implying it can
be admitted to storage unchanged.

Four fictional browser journeys stopped the actual local server, confirmed Save
refusal and unchanged stored files, then recovered every working input without
HTTP requests. They covered real desktop clipboard access, explicitly controlled
mobile denial and clipboard stall, and a **1,091,551-byte** oversized working copy.
Eight Node cases and three Python wrapper/argument checks passed. The controls'
scoped review was **8 for experience, 8.5 for function and 7 for appearance**,
not a whole-product rating. Independent review and final-source replays are
retained locally.

The combined source copy, based on committed provider-readiness changes plus the
reviewed held/backup runtime and test overlays, passed **2,026 Python tests with
five platform-inapplicable skips**. Exact source hashes and complete test output
are retained with that copy. Fatal Ruff, whitespace and the narrow public-boundary
check passed. The source result is separate from the published installers.

The real Linux Australia Word pack opened read-only in LibreOffice with a
five-page status and a readable first page. Linux desktop keyboard control timed
out before navigating to its final page; this native check is incomplete. The
independent retained-file rendering review covers the remaining pages, rather
than claiming a complete native desktop walkthrough.

The actual campaign also completed a stopped-server backup exercise through the
in-app browser. Save refused with the new recovery guidance; clipboard copying
and full manual selection remained usable. The clipboard contained all
**264,535 characters**, exactly matching the current working-copy JSON retained
privately by the operator. Earlier snapshots and every original field outside
the two deliberate record changes remained exact. The automation's notification
wait for a fresh file download timed out, but later inspection found the actual
file and confirmed its bytes exactly matched the reopened campaign. That attempt
succeeded; it is separate from the earlier missing-file observation, whose cause
remains unproven. Local text recovery also succeeded with the server stopped.
No hosted generation or outgoing communication was made by this operator or its
review team in this cycle.

### Atlas results survive passive checks; omitted coordinates stay omitted

A new adversarial witness found that a remembered packet's delayed inspection
could erase a completed source retrieval and its downloads. Passive inspection
now refreshes provenance without clearing the current output or consent. A
current inspection error remains visible, while explicit import, retrieval and
compilation continue to replace/reset the selection, even for the same snapshot.
Older and disposed responses remain guarded. This is packet-inspection recovery,
not qualification of every asynchronous or hosted generation operation.

Another witness found that a supplied start column with an omitted end column
was treated as reversed, because absence defaulted to zero. Range validation now
compares columns only when both endpoints are supplied; it preserves omission
and rejects explicit reversed ranges. The integrated validator already rejects
known-artifact path contradictions; additional regression coverage protects that
binding without a redundant implementation change. Original text, identities,
pointers, offsets and seven canonical fictional packet outputs remain unchanged.

Independent review passed **128 focused Python checks, 14 JavaScript cases,
13 actual isolated browser journeys and 316 additional matrix assertion groups**.
The omitted-column failures reproduced against the preceding source. Fresh UI
checks covered delayed success/failure, wrong identity, contradictory path,
changed snapshots, stale/disposed replies and explicit replacement. All owned
browser/server resources closed, with no private, credential, model or external
operations. The earlier passing broad suite missed these witnesses and is not
used to dismiss them. Final combined-source qualification remains a separate
recorded check; published installed previews are unchanged.

The final combined source copy passed **2,123 Python tests with five
platform-inapplicable skips**, plus fatal Ruff, whitespace and the narrow
public-boundary check. Its runtime/test bytes are bound to the reviewed source
and retained hash receipt. Qualification counts were added to this document
after the run; no executable or test bytes changed. These are source results,
not a new installer, customer-device or overall 10/10 qualification.

## 1 October — explicit casebook source choices and local backup recovery

Current development remains `0.5.4rc3.dev0`; the following changes are source
qualification, separate from published v0.5.4rc2 installers. A question can use
all supplied sources, explicitly chosen original sources, or none. Empty choices
remain unanswered. Exact question anchors and stable source identities prevent
changed questions, removed sources and reordered questions from silently widening
an earlier choice. V2 projects occupy separate storage so older previews cannot
save an unscoped reconstruction over them. Deliberately clearing every choice
permits a return to v1; retained workspace copies and historical reports remain
separate.

The first broad run passed 2,322 tests but was rejected after independent
witnesses found inconsistent reads during concurrent v1/v2 moves, invalid Unicode
preventing delivery of recovery results, and lost keyboard focus after source
mode/anchor confirmation. The repaired source uses one read snapshot, explicitly
labelled reversible escaping only for invalid code units, and retained question
focus. Direct inspection shows each original source without selecting it. Fresh
actual SQLite interleavings in both directions, UTF-8 HTTP jobs and report
save/reopen tests, and desktop/mobile keyboard and inspection journeys retested
those failures. Raw valid response text stays unchanged; retained incomplete
responses are not accepted answers and do not trigger automatic replay.

A real operator's casebook download produced no notification or observed file;
that attempt remains unverified. Selectable project backup text now provides a
local alternative. Campaigns and casebooks share the same recovery component.
It preserves current assembled inputs and unsaved source choices without
truncation or server admission; a pending source must first be added or cleared.
A separate adversarial probe found an older stalled clipboard request could
replace a failed-refresh warning. Every explicit capture attempt now invalidates
older completions, including failed attempts. Denied/stalled clipboard tests
retain full selectable text and the correct warning and focus. A successful copy
does not save the project or prove that a file exists; invalid scopes still refuse
restore rather than broadening the selection.

The isolated repaired source copy on the earlier `0f94301` base passed **2,338 Python tests with five platform
skips**, **22 JavaScript cases**, fatal Ruff, whitespace and the narrow
public-boundary check. Independent review separately passed 69 focused Python
checks, both fresh concurrency interleavings, actual Unicode recovery delivery,
16 shared/casebook/private race checks and desktop/mobile full-backup restore
journeys. The existing campaign recovery producer also passed four actual UI
journeys after the shared refactor. New receipts bind the shared dependency as
well as the component. The minimal prior-reader fixture was tidied only at EOF;
its closed identity and test pin were updated, preserving the original source
nodes and all four format/output fixtures. Final executable and test bytes are
bound to the corresponding qualification receipts. These are historical passes;
the cached-interface witnesses below supersede their source acceptance.

Capacity checks cover 20 questions and 300 fictional sources, duplicate source
identities, lazy 0/300/0 checkbox rendering, and both fresh mobile and desktop-to-
390px resize. A reproduced cached-width overflow was repaired without changing
source text or choices. Repeated performance checks still found first original
inspection can require substantial browser layout work. A private causal
comparison isolated nested preview virtualization. Making only the opened
inspection visible left residual layout spikes. The current source removes
casebook source-card virtualization as well; repeated and capacity checks must
qualify this further change.
Timings include scrolling and automation variation; a passing capacity test is
not a latency guarantee. Long picker scanning, singular/plural wording and document usefulness
remain refinement work. Independent bounded ratings are **7.5 for experience,
8 for functionality and 7 for appearance**, not a whole-product or 10/10 score.

The real Science Week casebook retained all 11 originals and every earlier
project field while three dated, bounded registration/mailbox/scientific
background records were added. A second SubjectNest casebook retained six
originals while the complete displayed public programme section was added as a
clearly described selection. Earlier notes and prepared reports remain history;
registration does not establish authority, a mailbox search does not establish
membership or delivery, and a source-only checklist does not establish
eligibility. Saved-database fidelity was verified independently of the failed
user-export observation. This operator/review cycle made no hosted generation,
outgoing communication or grant submission. Preferences and explicit model
selection stayed unchanged. Private business material is outside the repository.

RC3 preparation guards now reject non-regular or oversized manifests before
hashing and remove only a container whose exact ownership and policy were
verified. Independent synthetic refusal and source-map checks passed. This is
preparation evidence: no RC3 source seal, built assets, installed workflow or
upgrade qualification, clean-machine result or publication is claimed here.

### Current-main integration and cached-interface recovery

Two additional negative witnesses override the earlier green suite: an old open
casebook page could clear v2 choices with a same-revision v1 save, and could
restore a v2 backup as a silently broadened new v1 project. The original scoped
project survived the second path, but the new copy lost its choices. Neither is
acceptable recovery behavior. The witnesses used fictional workspaces only.

The current repair requires explicit format capability before returning scoped
projects or validating scoped backups. Shared request code never infers that
capability for old page modules. Scoped get/save/build/draft operations, including
the current stored document during a downgrade, use the same gate in HTTP and
the shared runtime. Returning an existing project to v1 additionally requires a
typed empty scope list. The current editor carries deliberate clearing through
navigation and backup recovery, and resets it only after successful saving.
Lossless current CLI operations opt in; Python callers declare capability;
the native source editor refuses scoped projects it cannot yet preserve.

Sinter pulled merged main `262235e0effc1c0252f6c13534333fb65216a0a8`, retaining
every pending runtime/test path and merging the overlapping documentation. This
introduces the shared runtime and native source window. Combined-source tests
and independent cached-interface probes remain separate from the earlier
receipts. No earlier browser pass qualifies the new installed native interface.

The Linux browser-only package menu command now explicitly selects browser mode
when Tk is omitted. Its source tests exercise the generated command through the
real launch adapters; default native packages retain their prior command. This
does not prove a package installation or graphical launch. Default native builds
need a matching toolkit and notices, an inspected build environment and actual
installed workflow evidence. The older private RC3 preparation is historical.

The operator used Sinter to edit and save the SubjectNest handover with a clearer
next decision, a category-context warning and four unassigned preparation
actions with unconfirmed internal dates. The complete prior document remains an
unchanged suffix; every prior report field and the earlier saved report remain
intact. The latest narrow read of the two supplier conversations returned only
their original SENT messages, not replies or quotations. No delivery, eligibility,
membership, quote, accepted action or model-quality conclusion is inferred.

The ERAIS per-completion runtime-identity proposal was retrieved from its exact
GitHub blob and matched the supplied 12-case fixture hash. It remains explicitly
pending installed-origin verification; current public 57-case compatibility
fixtures and live Sinter behavior were not changed by that proposal.

### Qualified combined source and actual operator recovery

Commit `5f7f9e2a7f9535c83ee683df68512f669b6c7df9` passed **2,596 Python
checks, with seven explicit skips**, 24 focused JavaScript test files, fatal lint and
the public-boundary check. All 348 files in the tested copy matched the committed
Git archive, including the existing checkout line-ending policy. Independent
cached-interface, capability, deliberate-clear, Unicode, keyboard, cancellation
and backup refusal checks cleared the repaired source. This qualifies those
source bytes, not a release installer or every optional capability.

The operator saved a real project's explicit question/source choice, prepared
and separately saved its source-only handover, closed both the browser tab and
the owned local server, then reopened the saved project. A complete manual
backup was restored through Sinter's file chooser as a new unsaved project;
the visible restored JSON exactly matched the captured recovery text. All seven
originals and the prior saved project remained intact. The browser download
event again timed out, so no downloaded-file success is claimed.

Replacing the restored unsaved editor exposed a native browser-confirmation
trap in the in-app browser: the popup blocked further tab controls, including
dialog dismissal and tab cleanup. The Linux keyboard tool also failed to
initialize its input portal and did not replay the input through another
backend. The popup needs manual dismissal; an accessible, non-blocking local
confirmation is being qualified separately. This failed operator step remains
evidence and is not covered by earlier automated dialog acceptance.

A bounded mailbox search subsequently found a supplier quotation in a separate
conversation from the original sent enquiry. Reading only the original threads
had returned no replies; that never established mailbox-wide absence. The new
original is retained privately with its source identity and dated selection.
No booking, accepted terms, confirmed internal responsibility or eligibility
conclusion follows from it. No hosted generation or outgoing communication was
made in these operator steps. Business correspondence remains outside Git.

Five independent capacity journeys retained every original, choice and complete
backup, but two first-inspection layout stalls measured 712 and 820 ms. These
negative timings remain open performance evidence. The bounded assessment is
still **7.5 for experience, 8 for functionality and 7 for appearance**; it does
not establish a product-wide score or a 10/10 experience.

### Source-picker checkpoint and separately reviewed recovery work

Commit `203a7dac77490a4215461db21394dae756ca3eb1` passed **2,617 Python
checks with eight explicit skips** and **243 individual JavaScript checks**.
All 352 tested files matched the committed archive. The earlier count of 24
JavaScript checks described test files, not individual test cases; the label
above is corrected without replacing that earlier source receipt.

Actual campaign replacement exposed a separate stale-capture defect: a new
campaign could retain an earlier campaign's visible backup text and refreshed
status. The private repair resets the capture when the working copy is replaced
and invalidates pending clipboard outcomes. It never clears the user's clipboard
or captures the new document automatically. Invalid imports retain the previous
editor and capture. An independent replay also found a pre-existing race: New
remained enabled during an Open request, and the older response then replaced
the blank campaign. Saved originals were unchanged. The narrow second repair
disables New during Save, Open and import, independently guards its callback,
and restores the control on success or failure without cancelling or replaying
requests. The original failure and repaired desktop/phone journeys remain
separate evidence. A capture is still a snapshot when editing within
the same campaign; refresh or copy deliberately to capture newer inputs.

The local casebook confirmation was revised after two adversarial holds. One
earlier version left report editing active during an approved request; another
explained session report recovery but omitted the explicit loss of unsaved
project and unadded source inputs. The final private version locks both regions,
starts on Cancel, states the discarded inputs and retains report-session recovery.
Its author and independent critic each exercised desktop and phone decisions,
request failure, focus return and report-only edits. These are source-level
checks; they do not erase the earlier in-app-browser trap or qualify an installer.

A separately reviewed question/evidence view exposes a report's own search
choices and exact original quotes without a current-project lookup or request.
Blank historical question wording and inconsistent references remain explicit
gaps. Original report text, pending document edits and Word exports are retained.
A bounded local CPU probe with one 200,000-code-point original, 20 questions and
three passages per question observed 138.5–141.8 ms before reusing each original's
character index within one inspection, and 2.1–6.8 ms afterward. Seven samples
per variant are a local processing observation, not browser latency, an installed
benchmark or a performance guarantee. Later inspections validate their own
originals again; the cross-inspection stale-source regression must pass.

The combined source, its deliberate merges and its regression results receive
a separate frozen receipt before commit. Optional hosted generation, additional
platforms and RC3 installed-release qualification remain outside these repairs.
No whole-product 10/10 claim is made.

## Quoted-budget foundation — 1 October 2026

Source commit `6e631e59a985295810206d989ca9d8613149e733` separates entered
quote amounts from an application-budget decision. The five campaign/v1 budget
fields, original prices, references, unknown amounts and historical costs remain
unchanged. Raw arithmetic above an entered AUD cash ceiling is an observation;
`over_ceiling` stays `null` because v1 does not qualify application amounts,
eligible costs or GST bases. Quote-basis review information is displayed separately
from readiness and currency review. It cannot be dismissed through a checkbox.

The Budget view uses compact cost disclosures, an explicit next-cost action,
exact-cent local arithmetic and current-answer review invalidation when active
costs change. Removing active costs also invalidates current answer reviews;
historical reviews remain retained. Newly derived briefs, reports and Word files
label quoted subtotals and explain unknown or mixed amount bases. Historical
saved JSON and literal user edits are not rewritten as new evidence.

The exact committed archive matched all **373** source-file hashes in the
qualification freeze after incorporating upstream launch/recovery fixes. That
combined source passed **2,735 Python tests, with eight skipped**, **280
JavaScript tests**, and **76/76** browser budget checks. The initial browser
attempt could not locate the environment's configured Chromium cache; its failure
was retained, and the successful rerun explicitly selected the existing installed
Chromium. Fatal Python lint and the public-boundary checks passed. Separate
independent reviews contributed **32** desktop/phone UI checks and **102**
hostile Decimal-context probes; the precision reviewer also ran **45** copied
regressions. These are source tests, not installed-platform passes.

A real campaign reopened at its saved revision with the original costs and
unpriced line intact. A read-only comparison against the stopped-server backup
found every row in the five local tables and the preferences bytes unchanged.
The brief clearly displayed the quoted-amount caveat. The in-app browser did not
confirm Word file delivery after the first attempt and one explicit cached retry,
even though Word capture passed in Chromium qualification. The existing local
exporter produced a validated private Word recovery file; that recovery is not
an in-app-browser delivery pass. No hosted generation or grant submission was
performed during this qualification.

Warm local processing observations used 100 fictional samples per action:
preparing the small fixture had a **0.240 ms** median, and preparing 200 cost rows
had a **2.730 ms** median. Word compilation medians were **2.691 ms** and
**2.830 ms** respectively. These are Python processing observations, not browser
load times, installed timings or guarantees.

The independent bounded-feature rating remains **experience 7 / functionality 8
/ appearance 7**. Open items include disclosure continuity after navigation,
brief count wording and embedded-browser Word delivery. A separately attacked
application-budget/v2 domain proposal passed its private checks but has no product
UI, guarded persistence, durable review history or installed qualification yet.
The full design gates remain open in [the application-budget design](APPLICATION_BUDGET_V2_DESIGN.md).
The published Linux-only 0.5.4rc2 preview is unchanged; this is unreleased
0.5.4rc3.dev0 source. No whole-product 10/10 or new installer claim is made.

## Quoted-budget navigation and brief qualification — 1 October 2026

Source commit `0719ddde04bacb5f046075a55d195121201a937d` preserves open
cost disclosures through section changes, Overview navigation and local
rerenders. This is session view state; backups and campaign/v1 records gain no
new fields. Explicitly replacing a campaign resets that view state. Decision
briefs use singular or plural counts, omit empty review items and label entered
funding amounts without assuming every route is a cash grant.

The first combined candidate was held: its full suite found an obsolete
`action(s)` wording assertion, and independent desktop/phone replays exposed
disclosure losses during rapid toggles and cost mutations. Those failures remain
retained separately. The repair captures live disclosure state before navigation
or rerendering, ignores detached controls and preserves deliberate next-cost
opening. The corrected assertion still requires held work to remain retained,
incomplete and excluded from current work; other preservation assertions were
unchanged.

The final committed archive matched all **373** files in freeze
`4979615af26acff4b0ce9db8e37d2be07d98d225e72139325fde8d7bf50ddc36`.
That exact source passed **2,776 Python tests, with eight skipped**, **280
JavaScript tests**, **146/146** budget browser checks, fatal Python lint and the
public-boundary checks. Independent desktop and phone navigation/mutation
replays passed **80/80** additional checks; brief, audit and generated Word
checks passed **109/109**. Composition review confirmed the narrowly changed
held-work assertion and the exact author and navigation repair files. These
counts qualify this source and these tested paths, not an installed release.

The real campaign reopened at its saved revision on this source. Section changes
and Overview navigation retained the chosen cost disclosures. Read-only DOM
inspection confirmed exact entered prices, including the blank unknown price;
the prepared local brief retained unknown totals and unresolved review items.
Afterward, every row and schema in the five local tables matched the pre-upgrade
backup, and preferences remained byte-identical. No campaign save, hosted
generation or submission was performed in this final runtime check.

Scope remains explicit: browser workbench cost changes reset current answer
reviews; direct CLI/Python campaign/v1 saves retain caller-supplied review flags
and require human review. Generated briefs include the quoted-amount caveat;
Word exports the current applied draft, including literal edits that may remove
it. The legacy raw ceiling comparison excludes non-cash support but does not
positively qualify other route kinds as cash grants. Its result is an arithmetic
observation; application `over_ceiling` remains `null`.

The strict bounded-feature assessment is **experience 7.3 / functionality 7.9 /
appearance 7.0**. Phone density, in-app-browser Word delivery, reviewed
application-budget persistence and RC3 installed qualification remain open.
Earlier headless Word checks and a validated local recovery copy do not prove
embedded-browser delivery. The published Linux-only **0.5.4rc2** remains the
available tested installer; **0.5.4rc3.dev0** is source development. This round
does not establish a whole-product 8/10 or 10/10 rating.


### 1 October: explicit Word recovery and usable campaign navigation

The reviewed composition starts from `901d4fb62424a1914d536449479d89c6e5ec40ee`
and binds its 17 changed code/test paths in the
[source acceptance receipt](releases/SINTER_SOURCE_WORKFLOW_ACCEPTANCE_20261001.json).
It passed 2,846 Python checks (eight skipped), 107 campaign layout browser checks,
50 Word recovery checks, fatal lint and the narrow public-boundary guard. Separate
critics passed 80 layout journeys plus six focused cases, 74 Word browser checks
and 17 filesystem/authentication/API cases. These are source gates, not final
installed-platform qualification.

The critic rejected an earlier restored-tab visibility gap and a later action
field wholly below a short phone screen at larger text sizes. Both negative
candidates are retained privately; the accepted layout reveals restored sections
and scrolls to the actual focused task below measured sticky controls. Owners,
unknowns, scopes, historical evidence, current reviews, dirty values and cost
row disclosure choices remain intact in the checked journeys.

Actual IAB use of the fictional draft saved an exact 2,697-byte Word copy, refused pending edits before
writing, and saved an explicitly applied edit as a distinct 2,731-byte copy.
Both files survived closing the app; the earlier file, five domain tables and
preferences stayed unchanged. The new operation performs a bounded private
local save, verifies ZIP integrity and byte readback, and shows an exact path.
It retains text after unconfirmed outcomes and never replays automatically.
Ordinary IAB Blob download delivery remains unconfirmed. Saving exact document
wording does not certify facts or embed the separately retained evidence pack.

Local preparation medians were 1.23 ms for the four-source fictional garden and
178.47 ms for a 1.98-million-character synthetic workload. The latter represents
only two of 300 repetitive documents in its selected passages; this is not an
exhaustive review, inference result or browser-speed benchmark.

Independent bounded scores remain below exceptional: layout UX 7.4/function 7.9/
aesthetics 7.0; Word recovery 7.0/7.8/7.0. These do not establish a whole-product
8 or 10. Dense forms, horizontal navigation discovery and real virtual-keyboard
use remain improvement areas. A separate Linux prototype proves bundled XCB
import and copied-workspace preservation on a Python-free offline Ubuntu base;
its native launch probe also exposed a shutdown callback error. Final combined
frozen builds, clean native shutdown, installed browser/recovery and actual prior
installer replacement gates remain open. No new platform or release is qualified.

A subsequent source polish removes the global claim that a file path was selected
when a user leaves the draft during a pending save. A fresh 21-check fictional
browser probe confirms the copy survives, Overview remains active and the
announcement says only that the copy was saved. The 34 focused Word state,
filesystem and route checks also pass. This small follow-on does not replace the
preceding composition receipt or qualify browser download delivery or an installer.

### 1 October: native signal shutdown repair, source acceptance only

An independent actual Tk/Xvfb probe reproduced the earlier deleted-scrollbar
callback error on the original source. The two-path repair schedules shutdown at
a safe idle boundary and coalesces repeated stop signals. It passes 43 normal
assertions across eight scenarios and five stale-timer cancellation assertions;
94 focused checks pass, with three host-display checks skipped. Fictional saved
records and exact preferences survive the checked paths, except an explicitly
requested user save. No provider, network or real-workspace operation was used.

These are bounded source checks. Direct external widget destruction and injected
timer-cancellation faults expose exception-cleanup limits in both the original
and repaired versions; probe cleanup is not counted as product success. Native
modal interruption and indefinite idle starvation are untested. A fresh frozen
installed build still needs clean shutdown, operator-workflow, saved-work upgrade
and artifact qualification; the previous prototype traceback remains retained.

The follow-on composition on `57781a8` passed 2,849 source checks with eight
skipped. Its initial run passed 2,842 checks and encountered seven fixture-setup
errors when the shared temporary filesystem filled; those same seven checks
passed on explicit retry in a private folder with available space. All 387 frozen
source paths remained unchanged. Fatal lint and the narrow public-boundary guard
passed. The [bounded receipt](releases/SINTER_NATIVE_SIGNAL_SOURCE_ACCEPTANCE_20261001.json)
retains the initial setup failure separately from successful source coverage.

### 1 October: real operator work after the source upgrade

The owned local runtime was reopened from the exact `299e1d3` Git archive after
a consistent private backup. All rows and schemas in the five saved tables and
the exact preferences remained unchanged. Through the actual IAB interface, the
operator reopened the saved Science Week campaign, inspected Sources, returned
to Budget and navigated through Overview. Exact entered prices, a blank unknown
price and the chosen cost disclosures survived the within-editor journeys.

The interface then prepared a local decision brief and explicitly saved a
4,493-byte Word copy. Independent file inspection matched the exact applied
title and Markdown through the compiler and confirmed ZIP integrity, the official
source link, unresolved applicant authority, unknown costs and unnamed ownership.
The five saved tables and preferences still matched the backup. No campaign save,
model generation or submission was performed. This is real local source-runtime
use; it does not qualify ordinary IAB download delivery or an installed release.
The fresh-start message is also corrected to name Your campaigns instead of
claiming that the campaign choices are above the message.

### 1 October: independent native qualifier review

The exact two-path native launch qualifier now refuses nonempty stderr, even
with a zero process exit, and retains the available original diagnostics through
cleanup failures. It seeds and reads a fictional Unicode casebook using the
actual target executable's offline CLI, checks type-sensitive identities, and
compares exact preferences, logical schemas/rows and persistent live-file
user_version, application_id, encoding and page_size before reopening.

The independently reviewed source passes 27 adversarial admission probes and
64 focused producer checks; the author's combined focused selection passes
158 checks with three display-dependent skips. Historical false admissions and
the original 266-byte frozen callback traceback are retained. SQLite schema
cookies, journals and physical file equality are outside this gate. No fresh
executable was supplied to these source reviews; installed native qualification
and the complete operator workflow remain open.

### 1 October: current installed Word gate, source acceptance

The eight-path installed Word qualification proposal is independently accepted
for ordinary source correctness. It requires the exact 53-operation catalogue
and current installed-workflow/v2 evidence: thirteen closed artifacts and
21 checks, including three actual Word files, pending-edit refusal, a distinct
changed copy, lost confirmation without automatic replay, and conservation of
all five logical tables, exact preferences and public settings. The producer
reads those files again after the installed process exits. Historical v1 contract
constants retain their original meaning; current source cannot fall back to v1.

The author's 366 focused checks pass; six retained ZIP-admission negatives
reproduce the corrected source gate. Independent ordinary review covers all
217 changed-module checks (one private socket-path setup failure passed on an
unchanged-source short-path retry) and inspects retained fictional DOCX bytes.
Earlier incomplete broader review work is retained and is not a completed
security assessment. No application binary or installed browser ran in these
source reviews.

The private combined source selection covers 2,948 checks with eight skipped.
Its initial run had 2,947 passes and one socket-path fixture setup failure; the
unchanged-source explicit retry passes. All 388 frozen source hashes remain
unchanged. A separate narrow terminal-notice policy review passes 160 ordinary
checks and 16 independent synthetic-archive probes. RC1/RC2 exclusions remain
unchanged; RC3 still refuses readline and checks actual Debian library,
copyright and referenced-notice bytes. These gate compositions are followed by
fresh qualification, rather than reusing an older installer identity.

The final main composition of the accepted Word gate and terminal-notice policy
passes **2,950 checks, eight skipped, no failures** in 168.41 seconds using a
short private test folder. All 388 pre-run source hashes remain unchanged;
changed Python lint, fatal repository lint and the public-boundary guard pass.
This clean run supersedes the earlier composition's setup retry for final
source coverage. It still does not qualify a frozen or installed artifact.

### 1 October: actual CLI envelope and retained installer refusal

The frozen `1b3189c5` candidate passed three copied-workspace upgrades and
three actual prior-DEB replacement upgrades, but its installed workflow refused
the first catalogue check. The application returned the documented complete
`sinter-operation-result/v1` success envelope; the qualification fixture and
validator expected only its inner `sinter-operations/v1` catalogue. The
original failed receipt and full actual response remain retained. This is a
qualification mismatch, not an application request or provider failure.

The independently reviewed two-path correction requires the complete envelope
and exact source-derived 53-operation result, including strict field sets,
versions, operation identity and boolean type. An unwrapped result is refused;
the public CLI and historical workflow v1 contract remain unchanged. The author
passes 383 focused checks and 14 actual-response probes; independent review
passes 232 focused checks. These accept the source correction only. A new
explicit source build and fresh installed workflow, recovery, cold-install and
native-display evidence are required; the failed candidate cannot inherit them.

### 1 October: actual Linux rc3 publication and retained limitations

The fresh `246b91e0ee432cb1f6f6fcd17425f55cd7a4cabe` Linux x64 preview is
published as `v0.5.4rc3`. Its exact eight public files, hashes, installed Word v2
and recovery journeys, all three actual prior replacements, bare offline install
and independently inspected mapped native launches are recorded in the
[publication receipt](releases/PREVIEW_0.5.4rc3_PUBLICATION_RECEIPT.md). Public
downloads match the sealed stage byte for byte and pass the scoped plan verifier.
The original failed catalogue gate remains historical; it was not relabelled.

Linux Python 3.10/3.13 each pass 2,965 tests with eight skipped, and Chromium
workflows pass, but the aggregate exact-source Quality run fails. Windows test
fixtures have encoding/POSIX scope assumptions; macOS 3.13 reports a genuine
concurrent local Word-save failure. No established macOS root cause or proof of
Linux unreachability exists. These failures stay retained and block additional
platform claims; the existing scoped policy admits only the tested Linux preview.
The release page separately discloses them and the native/browser presentation
scope. The immutable source ZIP retains prepublication documentation; current
main guides are updated after publication, without rewriting the frozen assets.

A fresh independent customer critique of the actual fictional installed screenshots
and Word/recovery artifacts rates UX 6.7, functionality 7.6 and aesthetics 7.0. It
identifies absent question-to-source/Word navigation and costly manual recovery.
This is a bounded offline workflow score, not a whole-product, native editing,
customer-device, live ChatGPT or hosted-model quality rating. Further improvement
continues; no 10/10 or completion of the broader quality goal is claimed.

### 1 October: post-publication source checkpoint and held prototypes

Source development is now `0.5.4rc4.dev0`; the published RC3 source and eight
assets remain unchanged. Exact source `e0076d2b450076d27ae226062c4df0ce8f334419`
passes 3,023 Python tests with eight explicitly scoped GUI/Windows-wrapper skips
in 160.21 seconds. Its 394 canonical files remain unchanged after testing. An
actual isolated Chromium Word-copy recovery journey passes all 50 checks with
no external requests, unchanged originals and byte-identical source inputs.
These are source regressions, not a new installer qualification.

The new exclusive-create/non-creating-open lock path retains ownership, link,
file-type and permission refusal, distinct saved copies and explicit retry.
Independent Linux review passes 93 focused tests and 50 synchronized/fault
checks. Independently retrieved, digest-verified artifacts from
[macOS source CI](https://github.com/neuroforge-io/Sinter/actions/runs/36849849584)
bind both Python jobs to `bd648f854aacdefafcf661172464c41b00e18e76`: each records
2,706 passes and 322 skips; all 29 Word-copy cases, including the original
concurrency test, run and pass without skips. The old E failure remains retained.
This supports the narrow source repair, without proving the original Darwin
cause, impossibility of intermittent failure, or installed macOS compatibility.

The historical D9 auditor now retains original package/source and clean-install
evidence, then refuses current-release staging with a friendly exit `3`. It
cannot manufacture independent review or E's workflow/v2 qualification. Its
complete 39-test authored proposal also passes independent replay and twelve
additional conservation/refusal probes; current composed tests retain the
separate reusable release-caller permission check.

Two private improvements remain held. Focused Word-navigation checks missed
40 historical report/qualification integration failures, prompting an explicit
new presentation identity and a separate closed workflow revision. Independent
review of a native-to-browser shortcut also reproduces a save committing after
the native owner closes. Neither prototype is in this source checkpoint or the
published preview. They require corrected integration and shutdown evidence
before adoption. The user's intentional app closure was not treated as a crash;
no physical app reopening or hosted generation was used in these checks.

### 1 October: recipient Word navigation source acceptance

The held Word prototype now has a separately reviewed integration revision.
Root's latest-main composition passes 3,109 Python tests with nine explicit
display/platform skips, 282 JavaScript tests, seven actual handover browser
journeys and all 50 Word-copy recovery checks. The independent reviewer closes
the unusual presentation-declaration and swapped-caption subgate witnesses;
the original 40 failures and earlier HOLD remain immutable historical evidence.

Generated handovers retain source identities, quotations and ranges while adding
bounded Word navigation and honest recipient instructions for omitted originals.
An explicit presentation identity and closed workflow/v3 keep historical report
and installed/v1/v2 receipts distinct. This is source-only `0.5.4rc4.dev0`; new
installed/upgrade, native-display and customer-device gates remain required.
The [source review](WORD_HANDOVER_NAVIGATION_2026-10-01.md) records the exact
evidence and separate real-case browser walkthrough, including remaining
retrieval and save-discovery shortcomings. The native-to-browser shortcut is
still held for shutdown repairs. No 10/10 or broader goal completion is claimed.

### 1 October: clearer report save and strict practical-use assessment

Current development labels the report action **Save to My workspace**; the
separate Word-save action and published RC3's old label remain distinct. Root
used the actual in-app browser on an isolated real-case copy: pending edits
blocked saving, applied edits saved to a new report, both older reports and Word
files remained exact, and Quit stopped the owned service cleanly. The temporary
agent tab was closed; the user's closed app and tabs were untouched.

The exact 399-file label proposal passes 196 qualification/presentation tests,
282 JavaScript tests, nine actual recovery browser journeys and six independent
historical/current/missing/mixed source-label probes. This supplements the
preceding full-suite checkpoint; it is not relabelled as a new full-suite or
installed pass. Report storage, applied snapshots and Word bytes are unchanged.

Independent critique of the earlier observed `e0076d2` real-case flow rates UX
**6.2**, functionality **6.5** and aesthetics **6.8**. Its retained shortcomings
include governing evidence losing to sender notes, selected sources and table
context being omitted, costly saved-output discovery and a manually written
decision summary. It did not operate the newer Word navigation or save label,
so it does not establish current whole-product scores. Those concrete gaps
remain improvement work; no 10/10 is claimed.

### 1 October: bounded native-to-browser source acceptance

The held shortcut now has independently reviewed admission and shutdown handling.
Root's fresh composition on main `917bb92` passes 3,173 Python tests with nine
explicit display/platform skips, 282 JavaScript tests and 44 browser checks.
Independent native-v2 review passes 19 read-only conservation probes and three
focused regressions: scoped projects and all 11 original documents survive native
open/save refusal. An unchanged native save may report an obsolete cached
revision without writing; no fresh-revision check is claimed for that no-op.

The actual in-app browser saves an isolated real-case handover with 16 exact
passages from eight of 11 retained sources. Its native Quit confirmation blocks
browser control, so user dismissal remains pending; no manual cancellation or
normal native-close pass is claimed. The owned service is stopped and cold
inspection verifies the saved originals/report. The user's intentional closure
was not treated as a crash or used to reopen their app.

Component scores remain UX 7.2, functionality 7.8 and aesthetics 7.0. Selected
but unused evidence, truncated table context, two-view coordination and fresh
combined installed/upgrade qualification remain work. The separate upstream
Linux-menu CI has actual package evidence for its own tree, without this native
repair; it does not qualify the combined candidate. See the
[source acceptance](NATIVE_BROWSER_REVIEW_2026-10-01.md). Historical failures,
published RC3 and its receipts remain unchanged.

### 1 October: retained evidence coverage and local context

Source-only casebook reports now distinguish sources that supplied an exact
quotation from selected sources that did not. Unknown passage lists, unresolved
identities and inconsistent search choices retain an unavailable state rather
than becoming a zero count. Original V3 failures remain in the private evidence.

Root's current-main composition passes 3,176 Python tests/nine explicit skips,
294 JavaScript tests, 51 new desktop/phone checks and the existing evidence-view
producer with actual Word captures and a cold source-app reopen. Independently,
82 read-only real-case checks reveal the retained original text beyond a table
heading cutoff without changing quotations, report history or AI preview.
There is no new root in-app-browser or installed pass: the earlier temporary
browser confirmation still needs dismissal.

Independent component ratings are 8.2 for correctness/claim discipline and 7.7
for sampled evidence-panel usability. Semantic retrieval, selecting new passages,
missing original bodies, maximum-size performance and broader release/customer
qualification remain work. See the
[bounded evidence review](CASEBOOK_EVIDENCE_CONTEXT_REVIEW_2026-10-01.md).

### 2 October: installed-menu diagnostic checker repair

Independent review reproduces three checker gaps: a callback error accepted as
success, a 78,000-byte stream reported as a 65,537-byte prefix and diagnostics
lost when cleanup raises. The narrow two-path repair captures the full observed
count/hash and a bounded reversible sample, pins the sole accepted console
notice to exact build-source bytes and preserves error/cancellation priorities.
Its source-only review passes 148 focused tests and 19 independent probes.
Root's current-main composition also passes those 148 focused tests. A separate
actual fictional source startup/SIGTERM observes the exact 72-byte notice,
exit zero, closed port/process group and no provider requests.

The accepted independent receipt is
`7b81559f2af1225a8f7ee0be631a30d09cb741e26174229830a7e76d76f6f511`.
This is checker correctness, not a new installed-app pass or a product rating.
Failed cleanup cannot certify future output from a still-live writer; that
receipt is refused. Historical receipts and published RC3 remain unchanged.
Fresh candidate packaging, both menu entries, native/browser handoff, recovery
and actual RC3 replacement still need their own source-bound execution.

### 2 October: upgrade presentation and preservation remain separate

The upgrade runner used its legacy-preservation flag to suppress explicit browser
arguments. Published RC3 defaults to native, so that behavior cannot exercise
its full browser workflow. The narrow correction uses the already verified
binary version for presentation while retaining legacy labels and preservation
checks. The original RC3 process-seam failure is retained; 151 focused authored
tests and 14 independently executed regression cases pass.

Independent source review is bound to
`0f3b33cc4af9d459c2f64b1d0398a657c96d429a09edf1ca15b240f22d3d00e1`.
Its process seams are fictional: no actual binary or installer ran. Historical
prior admission and receipts are unchanged. Exact RC3 admission, rich source and
scoped-v2 fixtures, capability refusal and actual package replacement remain
separate requirements before a new release can qualify.

### 2 October: accessible Quit and late-response source protection

Browser Quit stays available at phone widths and uses the existing accessible
in-page decision for pending work. Cancel/Escape keep inputs without a request;
an unconfirmed reply keeps inputs for explicit recovery. Native-owned browser
work remains while the native window decides. A confirmed standalone stop blocks
late page content/errors and releases its unload guard. Earlier race and unload
failures remain retained rather than being rewritten as passes.

Independent runtime review accepts V3. Root's current composition passes 185
focused Python tests, 294 JavaScript tests, the existing offline/confirmation
browser producers, 51 evidence-context checks and four actual source-process
save/quit/reopen/interruption launches. The reusable quit producer also passes
38 checks in eight desktop/phone journeys on current main. Four relevant
producers are added to routine Chromium CI with retained fictional artifacts.
No actual installed, physical native confirmation or new root in-app-browser
pass is claimed. See the [source review](BROWSER_QUIT_REVIEW_2026-10-02.md).

The first composition run hit a full temporary volume; its database/setup errors
and browser crashes remain recorded. The unchanged source passes with an owned
home-drive temporary directory. Wider `1382ce3` CI also has macOS and Windows
source-test failures under separate diagnosis. New installed/upgrade, bare-host
and platform acceptance remain release requirements; no new rating or 10/10 is
assigned from these bounded source checks.

Before adoption, the full current 411-file Linux/Python 3.12 composition passes
3,226 tests with nine explicit native-display/Windows skips in 283.40 seconds.
All canonical source hashes stay exact; 294 JavaScript tests, five workflow tests,
38 quit checks and the desktop/phone question-evidence producer pass. Actual Word
payloads and a cold source-app reopen retain their wording and identities. The
source receipt is
`dc4c9f258f630442c0268f1fc6681a1af3c0f6859d199a2882c91b97b7d0b25e`.
This later documentation note is separate from runtime and installed proof.

### 2 October: preserve platform-wrapper timeout evidence

The original `1382ce3` Windows launcher fixture timed out without retaining its
selected interpreter, child marker or partial output in the uploaded XML. Later
unmodified `465b437` Windows 3.10/3.13 wrapper cases pass; the historical timeout
remains unexplained. The narrow test-only change records executable/version,
arguments, working directory and bounded reversible output before assertions,
including when the fixture still fails at its unchanged five-second limit.

Independent root composition passes 140 focused tests with five Windows skips
on Linux/Python 3.12. Actual XML retains ten passing shell-wrapper observations
and a separately forced, expected timeout failure with exact non-UTF8 partial
bytes. Three finite controls exercise timeout, a surviving inherited writer and
large output. The independent receipt is
`f406feeccaa3013a33450394c07f8cd07d1a2e40d4926e509620f177a49b4550`.
Only the owned parent is killed/reaped with bounded cleanup; descendants are
unobserved. Regular-file snapshots are not final stream hashes, and retained
samples are bounded without claiming a hard disk bound for fixture spooling.
Application wrappers, runtime, workflow and old receipt schemas are unchanged.
No Windows reproduction, causal repair, installed pass or rating follows.

### 2 October: native cleanup test branches and uploaded child evidence

The hosted Windows failure assumed a live listener would always receive a second
shutdown call. The retained job log shows the listener already stopped after
failed cleanup. The replacement controls both live/stopped states and requires
their exact cleanup sequences, retained owner/runtime, unchanged unsaved inputs,
saved records and explicit retry. It does not widen an assertion to accept an
arbitrary call count or change application shutdown behavior.

The original macOS five-second whole-child timeout had no stage evidence; its
cause remains unknown. A separate finite 20-second process harness now covers
imports, fixture setup and process exit. Deterministic controls retain the
unchanged default five-second product deadline, while the real failed-GUI child
measures its deliberately short 0.02-second close refusal. No failed exit is
presented as durable recovery of in-memory inputs.

Current-main composition passes all 40 native-module tests in 18.47 seconds.
Independent current-source review also passes those 40 tests, five focused cases
and 16 byte/numeric bounds probes. Fourteen deliberately timed-out children retain
the identical primary exception, reversible partial bytes, stage snapshots and
secondary I/O/parse/write errors in actual uploaded-format XML. Prefixes are
bounded to 8,192 bytes, file reads to 8,193 bytes and cleanup measurements to four;
mutable file totals and an unobserved exit remain explicitly unknown.
Independent receipt:
`c55dbc0a22674f5c407982790c9b90b798679369726003071ab864114a5a29a0`.

Three default-xunit2 `record_property` compatibility warnings remain visible.
The actual XML retains the properties; strict schema compatibility is not
claimed. Production source, existing workflow and published receipts are
unchanged. Hosted Windows/macOS replay, actual installed/native/browser-owner
proof and final candidate qualification remain separate requirements.

### 2 October: exact published-RC3 fictional upgrade fixture

A separate preparation tool verifies the immutable published RC3 ZIP/DEB and all
388 extracted source files before creating fictional work. It retains full
originals, quoted ranges, v1 history and scoped v2 choices, raw reports separately
from their IDs, unknown/unassigned owners, stale source marks, typed SQLite rows,
persistent database metadata and explicit custom model preferences. It preserves
an untouched original and byte-identical replacement copy; checks use a third,
disposable copy with provider and external transport blocked.

Independent review accepts this source-fixture scope. Root's current composition
passes all 38 focused tests and creates a fresh exact-prior fixture. Its 15
protocol observations include 11 actual HTTP requests. Missing-capability v2
reads, validation, old-reader resaves, builds and drafts refuse; a capable but
unconsented draft also refuses. Wrong/duplicate capability headers and every
unsupported-reader route remain requirements for the later installed gate.
Independent review is bound to the retained handoff
`9e891886eb7e17993101172fc9bf353f9c8ad4a3e3326f11dbe535ff89b53842`.

Historical prior admission, receipt schemas and published assets remain exact.
The tool prepares data; it does not install or run either binary, replace a
package, admit RC4 or demonstrate customer desktop behavior. No model calls,
platform qualification or new quality rating follows. See the
[fixture guide](PUBLISHED_RC3_FIXTURE.md) for inputs and the remaining gates.

The first hosted `ba62150` replay exposes a new fixture-bootstrap failure on
Windows: Python 3.10 cannot initialize hash randomization, and 3.13 cannot resolve
its home directory. The parent supplied only a fixed search path. The narrow
correction also supplies Windows `SystemRoot` and a fictional `USERPROFILE`,
preserving the exclusion of caller accounts, credentials, model settings and
import overrides. POSIX remains exact. All 45 focused tests pass locally,
including seven bootstrap/refusal/contamination cases; actual hosted Windows
replay is still required. Original failed XML remains retained. The Linux-only
prior profile, published RC3 inputs and historical qualification stay unchanged.

The subsequent `7a65158` hosted run passes both Windows Python 3.10/3.13 jobs.
Each retained XML contains 2,913 passing cases and 373 explicit skips; all 45
published-RC3 fixture cases execute and pass. This verifies the source-fixture
bootstrap correction on those runners. The aggregate run still fails its two
macOS jobs, and no Windows installer is qualified.

### 2 October: remove local startup's reverse-lookup dependency

Both retained `c5c219a` macOS child journals finish imports but never reach the
saved-fixture checkpoint. They therefore show a startup stall before shutdown,
without identifying its actual Darwin cause. A finite owned reproduction locates
a concrete unbounded reverse lookup inherited from Python's HTTP server when
constructing the local workbench. The numerical-binding change removes that
descriptive lookup while preserving the actual socket binding and bound port.

Root's current composition passes 198 focused tests in 64.34 seconds, including
real IPv4/IPv6/localhost requests, source saves, Host/Origin/session checks,
native ownership, occupied-socket refusal and the Windows fixture correction.
The unchanged default five-second product deadline and measured 0.02-second
failed close remain distinct from the finite 20-second child harness. Finer
startup stages and a one-shot ten-second stack diagnostic make any further
hosted stall observable. Three existing default-xunit2 property warnings remain
visible; no strict-schema or warning-free claim is made.

Original forbidden-resolver failures and the initial diagnostic-producer failure
remain retained. This source fix does not establish the actual macOS cause,
qualify a platform installer or change any published receipt. Fresh independent
source review accepts this bounded change: 153 focused tests pass independently,
and real requests preserve the same security/save outcomes while the four
descriptive resolver calls fall to zero. A deliberately failed primary test
retains its ten-second stack and last completed stage before the unchanged
20-second timeout, leaving process exit and cleanup honestly unknown. Its review
also corrects a private evidence filename; the actual fixture guide's bytes were
preserved. Hosted macOS replay and installed qualification remain outstanding.

The subsequent `673cba2` hosted run passes both macOS 3.10/3.13 jobs. Each retained
XML contains 2,969 passing cases and 328 explicit skips; all 51 listener/startup/
native-handoff cases execute and pass. The intentionally failed graphical-launcher
fixture exits 1 after 329/282 milliseconds and retains its expected emergency
diagnostic. This is source-fixture evidence, not an actual macOS native UI or
installer pass. The original stall's precise cause remains unknown. The aggregate
run fails both Windows jobs on a newly added occupied-socket errno assertion;
their actual OS refusal and the source-test correction require separate review.

### 2 October: functional local recovery source rehearsal

Five new preparation paths add a separate Linux source-only campaign-v1 rehearsal
and a closed artifact verifier. Six actual source processes stop and reopen through
the browser, preserving complete originals, history, typed SQLite records and
explicit fictional preferences/model selection. The ten campaign phases retain
unknown versus unassigned owners, proposed dates and held/historical scope. A real
phone conflict and committed save/Quit with lost replies retain full local backups;
no automatic replay occurs during the documented 250-millisecond observation.

Independent execution produces 47 artifacts, six exit-0/closed-port observations
and a visibly expanded stale-source warning. All 45 separately resealed hostile
artifact mutations refuse. Root's current composition passes 160 focused tests in
18.39 seconds with no skips; fatal lint and whitespace checks pass. The three
original cleanup failures and earlier hidden-DOM visibility overstatement remain
historical evidence, rather than being rewritten as current passes.

The reviewed handoff is
`7ad0a03dcf539493adb9d6dc4141330539cd687fb0b0a6c1fbb80ae593a7a1d8`.
The source receipt explicitly keeps installed, candidate and release admission
false. Scoped casebook-v2 editor recovery, native ownership, actual installed
execution, exact published-RC3 replacement and the new canonical release gate
remain outstanding. No physical user app or provider is opened. See the
[recovery guide](RC4_LOCAL_RECOVERY.md) for the runnable subset and remaining gates.

### 2 October: occupied-port source regression on Windows

Both retained `673cba2` Windows XMLs fail exactly one newly added assertion. The
real occupied bind refuses with `PermissionError`, errno 13 and Windows error
10013; the test incorrectly requires errno 10048. Both startup-watchdog cases
execute and pass. The one-file test correction observes a real failed bind,
requires its identical exception to propagate without retry, checks the failed
socket is closed, and exchanges owned bytes through the untouched original
listener. It also checks the captured Windows error shape only after a real
occupied bind refuses. No runtime, deadline, skip or broad error allow-list changes.

Root independently verifies all 24 retained references and both actual Windows
ZIP/XML identities. A copied current-main composition preserves all 423 unrelated
files and passes 12 focused cases in 4.31 seconds. The mapped-error control
reproduces the original assertion failure and passes the correction with exactly
one real occupied-bind refusal. This is a portable controlled regression, not
Windows execution. Fresh hosted Windows replay and platform installer qualification
remain outstanding; the original failed evidence is unchanged.

### 2 October: literal Unicode in recovery evidence

The completed `6f890e1` source run passes both actual Windows occupied-port and
startup controls. Each Windows job instead has exactly two new recovery cleanup
failures: retaining a literal combining character through the old locale-default
proof writer raises `UnicodeEncodeError` under cp1252. Linux, macOS and browser
checks pass. The retained failed Windows ZIPs and XML remain unchanged.

The two-path correction gives the source-recovery producer its own explicit
UTF-8/LF atomic writer and explicit owned readers. It preserves original strings,
JSON serialization, historical transport helpers and all 21 earlier recovery
test/helper ASTs. It does not normalize, escape away or discard source evidence.

Root independently verifies the 103 pinned handoff references, all 424 candidate
files and all 422 unrelated source files. Its fresh copied composition passes
176 focused checks in 31.43 seconds with no skips. A separate untouched `6f890e1`
producer plus the new Windows-default controls reproduces exactly two failures
and one pass. Root also verifies all 47 actual Linux six-process artifacts against
the closed source contract; their receipt is
`1d62c10afb0ee82ddbd617debefd449091b0fe173a62cc90b6d3e8aa6cdb4a2e`.

These are source regressions and source-browser recovery evidence. Fresh repaired
hosted Windows execution and installed qualification remain outstanding. No
physical user app or provider request is opened, and no published asset changes.

### 2 October: repaired hosted source run and native-entry owner

The completed quality run `36907293494` at exact `7b0d786f79623711a336e0ad51f3d8e560616da0`
passes all twelve jobs. Root retains the API-digest-matched six original Python
ZIP/XMLs and browser artifact ZIP. Each Python job collects 3,344 cases: Linux
3.10/3.13 each pass 3,335 with 9 explicit skips; macOS each pass 3,016 with 328
skips; Windows each pass 2,971 with 373 skips. All 46 recovery and 12 binding/
startup case identities execute and match root's earlier focused XML on every
platform. This is actual source execution, not a platform installer pass. The
original failed runs remain immutable.

The separately reviewed V4 native-entry proposal repairs the V3 raw-state and
boolean-summary admission defects. Thirteen preparation paths add one owner and
a distinct closed archive-source route, preserving all 422 unrelated main files,
all 30 original native tests and their helper. Root verifies 407 author references
and 435 copied source bytes; the independent critic verifies another 62 references,
passes 529 unique affected tests in 41.70 seconds, confirms 115 additional semantic
probes and refuses 27 malformed real-archive variants. Probe totals overlap and
are not additional unique test cases. Reviewer setup corrections remain separate.

The retained Ubuntu 22.04 builder actually lacks Git. Its original Git route stays
unsupported. Host admission freshly re-archives real bare Git source; the distinct
inner archive route verifies complete source/version/producer bytes and origin
metadata. Four actual author success/refusal source runs retain all 56 original
lifecycle streams. An independent fifth inert run retains 14 more streams and
its actual full-ID removal/absence. No Sinter binary, native UI or installer runs
in these source mechanics. The former V3 malformed-state acceptance and nonquiet
source-Tk experiment remain historical negatives.

Independent acceptance is bounded to the source proposal:
`aea3582615bda7d9fe6b13effb1d469064a20c718a571f1d1fc49ce69a728bf8`.
A matching package's actual native-entry execution, combined browser/native
ownership, installed recovery, four-prior replacement including published E, and
closed RC4 canonical admission remain required. The guides
[owned container](INSTALLED_NATIVE_CONTAINER.md) and
[native entry](INSTALLED_NATIVE_ENTRY_TEST.md) specify runnable preparation and
these limits. No published RC3 asset, physical user app or hosted AI request changes.

### 2 October: scoped casebook recovery with conserved originals

The seven-path source proposal adds a distinct scoped-project rehearsal while
keeping the existing six-lifetime campaign journey mandatory. Its four additional
lifetimes cover selected, empty and all-source question scopes, stale reviews,
original Unicode evidence, an explicitly partial human draft, a saved handover
and its Word part bytes, one manual action edit, two-window conflicts and separate
clipboard/manual backup restores. Unknown owners, unassigned owners and unconfirmed
dates retain their meanings. Original snapshots, preferences and schema metadata
are checked before any supporting reader can initialise or migrate the workspace.

Independent review first rejected boolean/float values accepted as post counts,
revisions and selection endpoints. The rejected source and all original evidence
remain historical. The repaired contract refuses all 31 retained malformed
complete-artifact copies, including those ten numeric variants. Its 218 focused
checks pass without skips; the ten new assertions fail against the old parser.
All sixteen earlier scoped test/helper ASTs and 422 unrelated base files remain
exact. The accepted independent source review is
`773e63f2df140f7e867edd7b019f23b3753c69dbe51964601142a3d7937e6f9b`.

Root verifies all 114 author and 163 critic references, applies the exact patch
over `9722a58211c0f16f536af028a176839d28996b00`, and preserves 433 unrelated current
main files in its 440-file composition. A fresh 366-check affected suite passes
without skips. Its own default source rehearsal completes all ten lifetimes and
137 artifacts; closed semantic verification passes at receipt
`3b5dd4298165ac9d6f830028ee32e5f5eb07e0b73770a909ce6bd9ea09f60175`.
Root independently observes all ten PIDs gone and listeners closed. An initial
collector manifest-format error refused before starting an app and remains a
separate setup record.

This is source/browser evidence with fictional work, not a new installed release,
physical native editing, office rendering, model quality or grant-submission
claim. The physical user app stays closed and no hosted Sinter request is made.
Installed recovery, the four-prior replacement and final candidate admission
remain required. See [the scoped rehearsal guide](RC4_SCOPED_SOURCE_RECOVERY.md).

### 2 October: first private DEV native run and portable qualification checks

An isolated offline build at exact `9722a58211c0f16f536af028a176839d28996b00`
produces version `0.5.4rc4.dev0`. Its original same-run package receipt passes and
its 435 source files remain exact. The private Linux DEB is
`5ea2c05261d5bee46efdc132736c86375b24683333a8708d3967236f2b7df198`;
the package receipt is
`5bdf258261658de1ee77788e73ba536a8f6ee7b164248b0522bbdc60e98a8098`.
These assets are development rehearsals, not a published or admitted RC4 release.

The first actual archive-source owner installs that matching DEB and observes
four native invocations: create/save/WM-close, reopen/WM-close and the two existing
mapped SIGTERM launches. Exact fictional work and explicit model preferences
survive. All owning containers are removed without forced cleanup. The original
admission remains refused because `dpkg -r sinter` reports its shared `/opt`
parent is nonempty. The retained image's qualification interpreter occupies that
parent; independent probes confirm all three Sinter paths absent. The source
repair accepts only this exact observed warning at the exact removal command,
retains its bytes, and still requires actual status and independent absence.
The removal-only proposal preserves all seventeen original test/helper ASTs;
fourteen focused controls and 25 additional critic boundary probes protect that
narrow allowance. The actual historical
receipt stays unchanged; a semantic diagnostic with the repaired checker does
not qualify a new source or replace a fresh installed run.

Actual quality run `36912392945` at that same original source fails three new
fixture expectations in each macOS job and 52 new qualification-fixture cases in
each Windows job. No application `src` test fails. The exact failed logs and
API-digest-verified ZIP/XMLs remain retained. The source repair distinguishes
logical Linux paths from the host filesystem, serializes inventory names as
POSIX, and tests early unsupported-host refusal separately from mocked Linux
guard contexts. Portable byte/JSON/type/lifecycle controls remain active. Only
the actual unavailable process-group, FIFO and private-permission resources have
explicit, narrow predicates; no whole test file is skipped to conceal a failure.

The final eight-path proposal passes 344 unique Linux checks without skips,
Ruff F/I and formatting. Independent review confirms another 115 overlapping
semantic controls and 27 actual private Git archive refusals; those counts are
not extra unique test totals. All 427 unrelated proposal files and all 432
unrelated files when composed onto `e966d2ffc2ecb8fc4b15ca0252af92261735f20c`
remain exact. The independent source acceptance is
`a1e6bfe9fd6ff70d60b80f4bd32c10c5a0b8ab4ad6e85e36b2f13f61a0e0d88b`.
Root's combined current-main rehearsal and native qualification suite passes
562 unique checks in 29.03 seconds without skips.
Initial lint/format and reviewer cache-guard failures remain separate historical
records. Fresh combined hosted replay and all installed/canonical gates remain
required. The physical user app stays closed; hosted Sinter requests remain zero.

### Following hosted replay and scoped-reader portability, 2 October

Actual run `36918835852` at source
`2c4b8f54d65646486c8246301630e4ae38a07feb` completes all Linux and macOS Python
jobs and the Chromium workflow job successfully. Each Python job contains 3,674
cases. Linux has 3,665 passes and nine explicit skips; macOS has 3,346 passes and
328 skips. Each Windows job still has sixteen failures and 382 skips. The original
full Windows logs and independently API-digest-verified ZIP/XMLs remain unchanged;
this source replay does not qualify an installed platform.

The remaining Windows failures concern test and reader setup: actual POSIX child
capture in archive controls, text-mode newline conversion of synthetic original
preferences, host path syntax inside a mocked Linux container, and isolated CLI
children missing Windows Python bootstrap. A separate five-path QA repair keeps
all contract and privilege checks unchanged. The actual archive-child controls
require process-group support; their exact byte/origin checks also execute on
every platform through explicitly synthetic observations. Preference fixtures
write original UTF-8 bytes. Mocked Docker paths use their Linux namespace. Scoped
readers reuse the reviewed fictional environment helper, retain only required
Windows bootstrap, and request explicit UTF-8 mode under isolated Python.

Independent review accepts the exact source repair at
`a27e8687ec11ff76850ac06158afd63bbaf7b8f10badd4ef39ecbf893684c4c1`.
It verifies all 435 unrelated files against the 440-file original Git archive,
conserves all old function bodies except the three declared setup/reader changes,
and passes 349 unique Linux checks with no skips. Three new behavioral controls
fail against the old code; they are part of that total. Root's current-main replay
also passes those 349 checks in 25.22 seconds. The new CLI check operates four real
readers with a Unicode export path, original decoded JSON and the exact existing
progress diagnostics. Initial incorrect collector assumptions about empty stderr
and unescaped JSON, a formatter cache, and a wrong externally supplied manifest pin
remain retained setup failures; none is presented as an application defect.

A fresh private source rehearsal exercises all ten campaign/scoped app lifetimes
and 137 bound artifacts. Its source-only receipt is
`6df13c6f73cd01474832fa1957cecbac19b825b76c1028147dfa993132382c26`.
The independently observed ten PIDs are absent and all ten owned listeners are
closed afterward. Complete original work, selected/empty/all question choices,
uncertain save/quit recovery, historical reviews, separate restores and preference
bytes remain conserved. This proof binds the pre-documentation source snapshot
and its external manifest, not a later commit or installed binary. Fresh repaired
hosted replay, the three installed adapters and closed canonical release admission
remain separate gates. The physical user app stays closed and Sinter model calls
remain zero.

### Exact Windows CLI progress bytes, 2 October

Actual follow-up run `36923097221` at
`ad2d364eeac04eaf64f8074286894fde52a7881d` has 3,686 cases per Python job.
The six original API-digest-verified ZIP/XMLs and complete Windows job logs are
retained. Both Linux jobs pass with nine explicit resource skips, and both macOS
jobs pass with 328 skips. Each Windows job has exactly one failure and 391 skips:
the new progress-byte assertion expects LF while the four successful real Windows
CLI readers emit the actual CRLF lines. The Unicode export path, isolated child
bootstrap and existing source-reader behavior are preserved.

The one-test repair derives the exact expected line ending from the host platform.
It still compares complete UTF-8 progress bytes and accepts no additional output;
it does not strip, normalize or broaden installed Linux stderr policy. Independent
review `21be4443f637f6b4e2a8a04493c64b9ab9181db332aba7543df9b3c9ee6249d0`
checks all original collection references and passes the affected 56 Linux cases
without skips. Root's affected suite also passes 56 cases in 4.03 seconds. Fresh
repaired Windows execution is recorded below. No product source, user workspace,
installed receipt or published asset changes; the physical app remains closed.

### Exact-source hosted replay and unadopted upgrade blockers, 2 October

Run `36924989879` binds source
`b720b4a074b5d5d26b181e2db4f59d1c7a67b993`. All six Python jobs contain 3,686
cases. Linux passes 3,677 with nine resource skips, macOS passes 3,358 with 328
skips, and Windows passes 3,295 with 391 skips. The new actual isolated Unicode
reader check executes successfully in every job. The four additional Linux native
Tk source controls, Chromium workflows, RKC and local speech also pass. This is
source/portable execution, not an installed-platform qualification.

The first Windows 3.10 attempt has one older no-argument batch-wrapper timeout
at the unchanged five-second deadline. Its marker and expected stdout exist, but
the parent has not exited; surviving descendants are not measured. The original
failed XML and full logs remain unchanged. A single debug replay of that job at
the same source succeeds; the observed wrapper finishes in 1.915 seconds. No
assertion, deadline or skip changes. The timeout's cause remains unresolved.
Other successful jobs are retained from their original execution, not counted as
new repetitions. The final run's twelve job conclusions are successful.

Original and repeated artifact names coexist in GitHub. The retained positive
repeat is pinned by its actual upload-log artifact ID and API digest, rather than
choosing a filename. Both earlier collector assumptions and their raw downloads
remain separate failed collection attempts; they do not replace observed results.

Independent review refuses the separate, unadopted four-path replacement proposal.
Eight actual source lifetimes and 408 focused tests pass, but nine adversarial
witnesses expose four blocker families: legitimate removal diagnostics rejected,
cleanup hiding primary failures, inadequate visible saved-wording/uncertainty
checks, and unbound package/filesystem raw streams. Actual source rendering is
correct in those observations; the false admissions occur at verifier seams.
The proposal stays out of main pending repair and another independent review.
Fresh installed recovery, replacement, native handoff and canonical RC4 admission
remain required. No new installer is published; Sinter model requests remain zero
and the physical user app stays intentionally closed.

### Owned workflow browser seam, 2 October

The two-path source change adds an optional supplied browser session to the
existing 53-operation workflow producer. Its operating body, final cleanup,
historical defaults and receipt contracts remain unchanged. Independent review
`126a513157a563ccf0c6d1428d8a8f869a4219b900a46523c2ea21120ed84316`
accepts this narrow seam, verifies all 439 unrelated files and nine author
references, and passes 221 unique checks with no skips. Root's current-main
composition passes the same 221 checks in 35.46 seconds. The four new inert
failure controls are included in that total; supplied-session controls fail
against the old helper while omitted defaults stay unchanged.

The separate supplier's four inert interoperability controls preserve primary
errors and attempt context, browser and driver cleanup. They bind its intermediate
source snapshot only. This does not accept the final supplier or repair historical
default cleanup. Complete installed recovery, replacement, native handoff and
canonical release admission still require independent review and fresh installed
execution. Original fixture, collection and overlong Unix-socket setup refusals
remain retained; the successful short-path replay changes no assertions or
timeouts. No hosted generation or physical user-app execution occurs.

Fresh run `36929191732` independently binds committed source
`f61a19769fa86f86e7cde1996a784461474f1495`, before this browser seam is added.
Its twelve jobs all succeed on their first attempt. All six Python jobs retain
3,686 cases with the same explicit platform skips as the preceding replay; the
actual isolated Unicode reader passes in each. Linux's additional four Tk source
controls pass, alongside Chromium workflows, RKC and local speech. All twelve
artifact ZIPs are bound by original API IDs, sizes and digests. The initial
collection count error and empty supplemental test-name query remain retained
collector faults; the corrected reader records bind the actual six XML cases.
The development publication job is a no-op. Neither run publishes or qualifies
an installed preview or explains the older intermittent launcher timeout.

### Following source replay and installer-tool refusals, 2 October

Run `36932266041` binds the adopted seam at source
`77ce8d7e6b2710fd2256795966abd3c032f11be8`. All twelve jobs pass on their
first attempt. Each Python job has 3,690 cases: Linux 3,681 passes/nine skips,
macOS 3,362/328, Windows 3,299/391. The four new inert seam controls pass
everywhere. Original API-digest-verified ZIP/XMLs, browser artifacts and logs are
retained; Linux's separate four Tk controls also pass. Development publication
remains a no-op. These are source checks, not installed release qualification.

Three separate unadopted installer-tool proposals still refuse source admission:

- Native handoff review `de484cbf4c5a3373e938b9acbbc9bf9abc4a3463a417d72756d27164e0269a0e`
  finds primary cleanup selection, concurrent process aliases and incomplete nested
  schema/phase checks. Its 702 passes and four explicit GUI skips do not resolve them.
- Recovery review `2771b80956f0192482e2003bcce1fd239d06fab9afece516288452b864fb80a6`
  finds premature cache-empty admission, incomplete removal ownership/command binding
  and ignored empty directories. Its 236 passes and ten source lifetimes remain valid.
- Replacement review `87a7ccf67f22a9ccdd758af3f5b1fff0f106bc884192dfe1a29ebc77d2b583e0`
  finds unordered saved wording and diagnostic publication replacing the first failure.
  Its 505 passes, eight source lifetimes and earlier nine repairs remain valid.

These are verifier/producer defects; the observed normal source rendering remains
correct. Exact original witnesses, full exception chains, raw streams and review
references stay unchanged. Repairs proceed in fresh private copies against the
current source; their earlier executions are not relabelled. No proposal, installed
qualification or release pass is inferred from test totals.

The existing entrypoints also depend on original private locations and live host
tools. A separately reviewed design specifies finite read-only archived-evidence
revalidation with opaque original labels and complete retained product bytes.
It permits no archive commands or live historical-port checks, keeps the existing
64/256 MiB bounds, and records external qualification infrastructure separately.
Its twenty controls are design requirements, not implemented passes. Canonical
RC4 admission and actual matching installed execution remain pending. The physical
user app remains intentionally closed and Sinter model requests remain zero.

### Corrected native handoff source adoption, 2 October

Independent review
`b4d478043230cc988faf7d44f2d47186a0bd584c1449da5200ba99ba98acbe6b`
accepts the corrected four-new-path native handoff proposal against the exact
`77ce8d7e6b2710fd2256795966abd3c032f11be8` baseline. All 441 baseline files
and 3,345 original function bodies are conserved. The original refusal remains
unchanged. Root verifies all 5,678 author, historical and independent reference
occurrences, retains their complete bytes, and declares the two later main
documentation changes separately before applying the exact reviewed patch.

The independent focused replay has 747 passes and four existing explicit GUI
skips. All 22 original malformed literal/full-fixture witnesses now refuse through
their intended identity, type, nested-schema or phase checks; complete positive
fixtures pass. Seven inert native-driver cases preserve the first exception and
attempt destruction, including withdrawal and construction failures. Forty
additional controls pass, including allowed later PID reuse and collisions across
different process namespaces. A real source HTTP quit/cancel/interrupted-request
control preserves disk state and closes its owned listener and thread. These
separate controls are not added to the focused test total.

Root's current-main composition passes 364 focused tests with no skips in 9.00
seconds. This includes all 184 new-module cases, the four supplied-session seam
cases and the shared entry/archive/container contracts. Formatting and static
checks pass. Source adoption does not admit an installed native/browser journey,
a final package, an archived historical qualifier or a new release. The physical
user app remains intentionally closed; no Sinter provider/model call is initiated.

The corrected recovery proposal remains held after its independent 260-pass,
ten-lifetime source replay: five malformed removal-stdout records still pass its
consumer. The narrow complete-stream repair and replacement's ordered-wording
and publication-error repair require fresh independent review. Historical failures
and all corresponding source receipts remain unchanged.

### Corrected replacement source adoption and native hosted failures, 2 October

Independent replacement review
`b7e926e75301878d4b0a5de5dea5012584f82e8bdd0b4ed626c9a130ecc06cfa`
accepts the exact four-new-path patch. Its 523 unique tests pass with no skips.
Five preserved latest witnesses change from false admission to the intended
refusal: original/applied wording must keep order and multiplicity, and failed
diagnostic publication must preserve the original error and still attempt the
separate failed-response publication. All earlier nine targets and their 41
surrounding controls, plus ten filesystem controls, remain protected.

Eight fresh source lifetimes across the four pinned published priors pass; 33
hostile views of the fresh RC3 source run refuse. All 16 observed app/collector
PIDs disappear, eight app ports close, and observed workers, sockets, threads,
relays and browser temporary files close. Six older app stderr streams are empty;
the two RC3 source streams retain their exact 72-byte normal notice. This is
different from the 80-byte package-removal warning. No installed replacement is
observed or inferred. Repeats and distinct control groups are not added to the
523-case total. Reviewer cache/setup/reader-bound refusals remain retained.

Root rechecks all 13,785 hash-bound author/historical references and 7,658
byte/hash-bound review references. Its separate private retention also includes
an oversized negative test fixture; retaining it does not admit it to the bounded
public evidence transport. All 441 original source files match the reviewed
baseline. Root declares the four adopted native files and two documentation
changes as a separate later delta, then applies only the reviewed replacement
patch. The combined current source passes 711 tests without skips in 17.64
seconds. The first root run's two Unix-path-length fixture refusals remain
unchanged; a shorter private pytest base directory fixes the setup with no
assertion, timeout or source change. Static and formatting checks pass.

Hosted run `36938320802` at native-source commit
`0bfac7e9e3d9d1500a226536af25e3e0d3449133` is **failed**. Each Python job
has 3,874 cases. Linux passes 3,865/nine skips; macOS passes 3,546/328.
Windows 3.10 and 3.13 each have four new native-control failures and 392 skips:
two real source HTTP timeouts, an incomplete mocked Docker identity, and an
unavailable POSIX process-group call. Browser workflows, RKC and speech pass;
aggregate verified-package staging is skipped. Original API-digest-bound XMLs
and full failed logs are retained. These failures require diagnosis and fresh
hosted replay; they are not marked fixed, excluded wholesale or explained by
passing Linux checks. No new installed release is qualified or published.

### Corrected recovery source adoption, 2 October

Independent review
`cca3ca90bc53322d5188588093f4b5799b6938e009c871e3f1bac52707edeba9`
accepts the narrow complete-stdout parser repair. The original five malformed
saved records fail their refusal assertions against the previous source and all
refuse against the repair. Its 27 independent controls and 266 focused source
tests pass without skips. Complete nonempty, non-UTF-8 and 65,536-byte stdout
remain accepted; the exact 80-byte package-removal warning, ownership, unique
command binding, file absence and first-failure policies remain unchanged.

All 445 frozen source files match, with 438 unowned baseline files conserved.
The cumulative seven-path patch includes four new QA paths and only the reviewed
optional seams in three existing QA helpers. Root rechecks and retains all 7,838
author/historical and 3,557 regular reviewer byte/hash references. Special
adversarial entries remain explicitly recorded without opening them. Root
declares the eight adopted native/replacement files and two documentation changes
as a later delta before applying the exact recovery patch.

The combined main-workspace checks pass 973 unique tests with no skips in 83.97
seconds; formatting and static checks pass. This is source composition, not
installed execution or a product-performance benchmark. The prior ten-lifetime,
21-RPC source browser journey remains historical before the final one-call parser
repair; neither author, reviewer nor root reruns or relabels it as fresh installed
proof. Reviewer setup failures, the corrected removal-warning length and the
disjoint concurrent replacement work remain retained. No whole-workspace-clean
claim is inferred from a frozen-proposal check.

The native Windows failures remain a release blocker. Their full traces show the
HTTP bodies and cleanup pass before the closed-port postcheck times out; this
does not demonstrate a request-startup defect. A separate QA-only portability
repair is under review. Canonical RC4 admission, the finite historical consumer,
matching final package and every actual installed gate remain pending. The
physical user app stays intentionally closed and no hosted model call is initiated.

### Native QA portability and evidence transport adoption, 2 October

Independent native-QA review
`8baaf608ea1d0a3a2221a8379c1dc422a6f6b7b0b3386d4a876e8aac185f674d`
accepts the exact one-test-file patch: 760 source checks pass, with four unchanged
GUI opt-in skips. Four controlled original platform failures are reproduced before
correction; 16 additional independent controls pass. Both actual source HTTP
journeys retain their request and cleanup assertions. Their final check requires
the owned descriptor closed, server thread stopped and exact address reacquired;
a timed-out connection does not prove closure. Windows uses exclusive binding
before bind; mapped API-order controls do not establish an actual Windows pass.
Production port probes, product deadlines, source modules and receipt schemas
stay unchanged. Only the unavailable POSIX process-group resource skips on
Windows; three portable malformed-child controls remain active. Original hosted
failures and reviewer setup faults remain retained.

Independent catalog review
`79da87a926af6880102094af9b867803d340f72a003a7f0d492c0a0089b1714c`
accepts three new paths as transport only. Its 165 unique source checks comprise
89 owned and 76 unchanged shared controls, without skips; 12 additional
independent controls pass separately. Two-root relocation, independently approved
authority, opaque original labels, 11,001 scoped roles sharing one approved blob,
intercepted read-only operations and descriptor failure cleanup are verified.
Transport sets semantic, historical and installed qualification to false. It
does not complete the earlier 20-control design or prove the final release
inventory fits the unchanged 64 MiB member and 256 MiB bundle limits. Unsupported
physical reader capabilities refuse; portable schema controls remain active.

Root verifies and retains 3,318 native-QA and 3,192 catalog byte/hash references.
It declares the 13 later paths between their exact `0bfac7e` base and main
`427baeeb9a60b45f5eeaac9a1f12fda0883ee697`, then adopts only the four reviewed
paths. Their literal bytes match the reviewed manifests. Combined source checks
pass 466 unique tests without skips in 12.32 seconds; static, formatting, Python
3.10 grammar and public-boundary checks pass. This measures test execution, not
product performance. An initial root invocation selected a nonexistent archive
test filename and collected zero cases; its complete refusal stays retained.
The corrected invocation changes no assertion, deadline or source. A root
metadata lookup also initially assumed the wrong manifest shape; the corrected
lookup verifies the original unchanged bytes.

Actual Windows replay, matching final installed execution, complete raw gate
admission and independent final artifact review remain pending. The user app is
still closed and no Sinter model request is made. No candidate is published or
graded 10/10 by these source checks.

### Optional browser dependency in recovery source controls, 2 October

Independent review
`fba6e47b00578cd668ecebfef69eb2b0a375ec5f75056005111e43f13b5eb801`
accepts one test-only patch against `c334ba8d137566844ae2c6b3535873ce10989978`.
Ten inert controls previously failed or errored when Playwright was absent; all
ten now pass with the real package explicitly blocked. The injected API refuses
unconfigured browser work, restores original module objects after each control,
and leaves the production dependency guard and existing assertion bodies intact.
Root's 142 unique focused source checks pass without skips in 2.23 seconds; the
separate ten-case blocked-package replay is not added to that unique total.
Static and formatting checks pass. Root retains 2,056 author/reviewer byte/hash
references. An initial root invocation named a nonexistent shared test module,
collected zero tests and refused; the corrected selection changes no assertion.

Actual hosted run `36943835921` against the preceding `c334ba8` source still
fails its six Python jobs. The native test group has no failures on Windows:
195 cases pass and two exact unavailable POSIX-resource controls skip per job.
Other recovery/replacement portability failures remain recorded, including an
unexplained Windows idle-relay cleanup refusal. This new test-only adoption does
not erase those failures or qualify an installer. The user app remains closed;
no model request or release publication occurs.

### Before/after host-tool observations, 2 October

Independent root review
`c054739c1a9c8d373cd6653e9a2d63e0d1190e71209c2a94fbbf8d3d3d229e14`
accepts the bounded eight-path source change against frozen `427baeeb`. Its
453-file base and 456-file proposal conserve 448 unowned original files and
canonical Git modes. The exact patch replays; 805 canonical source checks pass
without skips in 14.84 seconds. A declared composition with seven later main
paths passes 1,049 unique source checks without skips in 71.15 seconds. These
are overlapping source runs, not additive installed or performance evidence.

The native browser and replacement outer records require new explicit schemas
with independently read before/after fingerprints. Missing, changed or untyped
after identities refuse; actual selected Docker, Chromium, Python and Playwright
Node/CLI identities stay within the declared trusted host/library/daemon boundary.
Host executable payloads are not copied, and the public 64 MiB member/256 MiB
bundle limits remain unchanged. Source fingerprint reads have a separate bounded
limit and confer no executable, library or daemon byte closure.

Twelve separate independent controls pass. Two demonstrate remaining limitations,
not successful qualification: native failed sidecar writes retain the first
exception and later errors but carry no complete unpublished records; the unchanged
final native owner-run diagnostic write can obscure the earlier failed context.
Only replacement currently carries complete unpublished bytes through its explicit
failure object. Both native boundaries remain repair work before a complete
failure-conservation claim. The narrow acceptance does not mark them fixed.

Root retains 10,304 author/reviewer byte/hash references. The author's sealed
inventory remains unchanged. Initial reviewer comparisons incorrectly treated tar
permission metadata as canonical Git modes; the corrected comparison uses
`git ls-tree` and preserves the original refusal. Twenty generated compiled caches
match their exact sources and remain in the two reviewer runtime views; those
views are explicitly not closed release source trees. No source bytes, assertions
or deadlines are altered to conceal either refusal. Static, formatting and Python
3.10 grammar checks pass. Actual final installed execution, bounded public inventory,
release authorization and publication remain pending. The physical user app stays
closed and no Sinter provider call is made.

### Recovery/replacement platform source repair, 2 October

Independent review
`d2a63301fefba1769b9073eb84fa768ea0dc1f5aacbd110f7a5874eefd7f6c16`
accepts three paths over exact `c334ba8` plus the separately reviewed optional
Playwright fixture patch. All 453 unowned base files and canonical Git modes are
conserved. Exact original and declared `ad4b3da` patch replays match; the later
ten-path host-observation adoption is explicitly separate. The original failed
platform runs, incomplete log captures and reviewer setup refusals remain retained.

Portable malformed-stream/parser controls use explicitly synthetic command rows;
three separate actual POSIX-child cases preserve complete real streams and
ownership checks. UTF-8 fixture reading is explicit, short owned Unix-socket
directories replace long pytest paths, and recovery helper reads/writes close
their real SQLite connections while preserving transaction behaviour. The
independent reviewer reproduces 26 missing-killpg, one encoding, three long-path
and four connection-closure failures against old source; their corrected controls
pass. Under mapped unavailable OS resources, 141 portable recovery controls stay
active and exactly three POSIX children plus one Unix relay skip. This is mapped
source evidence, not an actual Windows/macOS pass.

The unchanged Windows idle-TCP cleanup still requires `(0, 0)` within the unchanged
deadline. Transparent test instrumentation calls the original socket shutdown,
retains its actual return/error identity, re-raises unchanged exceptions and records
surviving owned stacks/socket state. It does not repair, skip or hide the actual
`(1, 1)` failure. The independent review passes 509 unique repository controls and
five separate wrapper/deadline/real-SQLite controls. Both 403-case normal and
blocked-Playwright replays pass without skips; those repeats are not added to the
unique total. Root retains 45,641 author/reviewer regular byte/hash references and
keeps special-node inventories lstat-only.

Root's declared current-main composition passes 1,159 unique source checks without
skips in 27.15 seconds; static, formatting and Python 3.10 grammar checks pass.
Fresh actual hosted platform diagnosis remains required. No installed gate,
release readiness, model quality or product-performance claim follows from these
source timings. The user app remains closed and no Sinter provider call is made.


### Native diagnostic-publication source repair, 2 October

Independent source acceptance
`8bf482fd8387a4c4c04a1c1c6e26bb577e83e9437c9bae8749a14a40faaaa1b0`
verifies the original five-path proposal over exact `9569abf` and its separate
three-path envelope correction. The full original source, raw failed records,
filesystem byte identities and earlier HOLD verdict remain unchanged. This
source repair supersedes the two native publication limitations recorded above;
actual native installed execution remains a separate requirement.

Native outer, client, initial/final owner-run and final browser records now use
the existing bounded evidence publisher with source-fixed native writers,
serializers and failure schema. Replacement defaults remain unchanged. A failed
write carries the complete original unpublished bytes, count, digest and base64
through its typed failure even when the fallback also refuses. The first
exception and later write/close errors are retained. A real owned POSIX filename
containing byte FF reproduced the old CLI UnicodeEncodeError; the correction
exits 1 with the identical typed failure, full diagnostic bytes, valid UTF-8 JSON
and lossless filesystem identity. Valid Unicode output stays byte-identical.
Both renderer refusals retain typed original data and secondary errors without
claiming successful stderr publication.

The independent exact replay passes 600 unique source controls plus four new
filesystem/SIGINT controls. Its 48-case focused run overlaps that total. Current
main advanced to `d9a643c` during the authorised fast-forward pull; a separate
composition preserves its cancellation classes and exact Windows Path assertion.
That composition passes 605 source controls without skips in 12.83 seconds.
None of these timings is product-performance, actual Windows, installed, upgrade,
cold-install or release evidence. The known synthetic stale-frame/reused-exception
edge remains an explicitly unsupported occurrence, not a proven native lifecycle
failure. The physical app remains closed and no Sinter provider request is made.


### RC4 original-workflow and candidate source composition, 2 October

The separate RC4 candidate authorizer, manifest-dispatch correction, interrupted
descriptor-cleanup correction, workflow owner and source-catalogue alignment are
now composed against exact `3ab6a20077f37b79ee6a814619487692d2c10992`. The original
failed controls and all earlier release assets remain unchanged. Independent
source acceptances include cleanup `dbb1a930...`, workflow `ca99c434...` and
catalogue alignment `b221cbdd...`; their complete pinned records are retained
in the operator evidence.

The unchanged trusted catalogue parser recognizes the exact 53-entry earlier
profile and 54-entry funding-enabled profile. The workflow receipt and candidate
gate now use the actual source count, while preserving 22 named UI checks and
13 retained roles. This does not mean every catalogue operation was exercised
through the interface. All other workflow producer and contract code is conserved
from the independently accepted correction, except the declared source-count
functions. UID 0 is refused before preparation. Failed receipt publication keeps
the original exception, complete serialized bytes and later publication outcomes.
The manifest reader similarly preserves its original read failure across an
actual interrupted descriptor close. Earlier preview policies remain unchanged.

The exact private composition passes 722 source cases without failures or skips.
Formatting, F/I lint, Python 3.10 grammar and the public boundary pass; this is
source evidence, not installed execution or product-performance evidence. Public
inspection remains byte-integrity inspection and cannot substitute for original
installed qualification. The actual final RC4 build, installed workflow, prior
preview upgrades, native/recovery checks, cold install and independent final asset
review remain required. The current version stays `0.5.4rc4.dev0`.

The hosted source run for `3ab6a2` (36959550809, attempt 1) ended cancelled. Only two of six
expected primary test artifacts were present, so their original Windows records
are partial observations and establish no complete platform pass. The reason for
cancellation is unconfirmed. Development publish run 36959551002 skipped native
build, qualification and publication; its success was a no-op. Those complete
available raw records remain pinned separately. The physical Sinter app remains
closed after the user's normal close, and no Sinter provider call is made in this pass.


### Relay cancellation source convergence, 2 October

The independent fourth correction acceptance `d2c15651...` retains every earlier
failed proposal. Its actual default Unix-socket queue control reproduces the old
false connection admission and retains the new genuine EAGAIN refusal, identical
exception object, original timeout and complete descriptor cleanup. A successful
retry is explicitly initiated only after the queue is released; no uncertain
operation is automatically replayed. First read/connect/send failures keep later
timeout-restoration and socket-close failures.

Separate current-main acceptance `171844c4...` preserves the native diagnostic
publisher, original tracked cleanup and direct legacy wrapper. The actual request
handler supplies the cooperative reader, using one shared stop event and preserving
receive flags. Idle connections close without errors; consumed partial headers
and bodies retain their original failed framing status. Actual wrapped late data,
EOF and client backpressure stop without presenting an uncertain partial write
as completion. Exact focused source replay passes 291 checks plus 16 independent
controls; the dependency-blocked 45-case replay overlaps those checks. Earlier
1,015-case evidence belongs to final production code before a test-only consumed-
header barrier; its original test bytes and source manifest remain retained.
The initial four composition-fixture failures remain unadmitted historical
records, not silently rewritten successes.

An incoming main update changed only the diagnostic filesystem-admission test
fixture. It uses a Unicode directory only after an actual EILSEQ refusal and
retains other failures. All 51 affected native-publication source checks pass
after integration. The production relay paths are unchanged by that update.
These are source results only; the final installed and hosted regressions remain
required. The physical app stays closed after the user's normal close and this
work uses no Sinter hosted generation.

After both accepted families and the incoming filesystem-test update are combined,
1,456 unique relevant source cases pass without skips in 71.60 seconds. The
changes preserve the original raw source failures; these timings do not establish
product performance. Formatting, F/I lint, Python 3.10 grammar and the public
boundary pass. Installed qualification and final asset publication remain pending.


### Hosted-source refusal and portable source correction, 2 October

Exact `3132ad91c89680e98ab5c8ac739c23b696586f7a` Quality run 36964758587,
attempt 1, ended FAILURE. All six Python jobs failed: five cases on each
Linux/macOS version, 29 on Windows 3.10 and 49 on Windows 3.13. Chromium,
RKC interoperability and all three speech jobs succeeded; verified-source was
skipped. Original complete failed logs and ZIP/XML uploads are retained.

Earlier `f73cf45b5f14e357f4a2aede4b554c56d495478e` run 36962603645,
attempt 1, passed all 12 jobs. Each original Python phase reported 4,607
unique cases with its platform skips; five native GUI source checks remain
a separate phase. This is a prior source baseline. Earlier run 36959550809
attempt 1 cancellation and its externally started attempt 2 failure remain
distinct observations. No failed result is replaced by a later pass.

The accepted workflow correction changes two source test files only: real
private short ownership roots, native absolute fictional paths, explicit
resource admission and deterministic reversible diagnostic refusal. Independent
replay plus controls passed 199 unique cases and retained every original
assertion. The accepted relay correction changes one source test file only;
298 relevant cases plus six independent controls pass. It reproduces the
original selector failure and observes actual unread TCP backpressure before
checking cancellation or the unchanged 0.25-second operation deadline.

The accepted manifest correction changes only the metadata reader and its
source controls. It passes 299 relevant cases plus six independent controls,
retaining real replacement/rewrite/descriptor failures and the first error.
The official pinned CPython implementation supports the Windows timestamp
mismatch inference; original runner stat field values remain unknown. Shared
file identity and full channel-local snapshots remain bound to the original
pinned-byte release authorization.

These separate family replays overlap the joined source tests; they are not
additive coverage. Two original Windows batch launcher timeouts still have no
proven cause; their five-second limit is unchanged. A new exact-source hosted
run and actual installed qualification are required. Sinter and the real
workspace remain closed; this pass makes no hosted model calls.

See [the source portability record](RC4_SOURCE_PORTABILITY.md). The original
191-reference CI capture manifest is
`c2436f643cee85df468337ce2e1a7accf02b6df7078036770704207e6a8a26f3`.
Development publication remains a no-op. Published RC3 assets are immutable;
there is no new admitted installer or higher product score from this source pass.

The joined 16-file Linux source replay passed 1,583 unique cases, no failures,
errors or skips, in 80.17 seconds. Three Pytest diagnostic-property/JUnit format
warnings are retained in the complete raw output and XML. F/I, formatting,
Python 3.10 grammar and the public-boundary check pass. No score is raised by
this source result; exact-source hosted and installed checks remain required.


### Follow-up hosted result and final candidate source

Exact `079263662b079051aeb2fedd361dfd90e1cc3636` Quality run 36969962677,
attempt 1, ended FAILURE. Both Windows Python phases have one remaining
cancellation-fixture setup failure; its actual failed-run buffer, byte and mode
observations remain unknown. Linux and macOS Python phases, Chromium, RKC and
all speech jobs passed, retaining their original skips and warnings. Five Linux
native GUI checks form a separate source phase. The dependent verified-source
job was skipped. All original logs and artifact ZIP/XML bytes remain retained.

The previous 23 Windows manifest failure identities now pass. The two earlier
Windows 3.10 launcher timeout cases also pass on this exact source; their earlier
cause remains unproven. Explicit POSIX-resource skips do not qualify Windows
ownership or installed behavior. The follow-up capture handoff is
`2a4017b3b31198ac6a47190b2216c267704678628b8f9d042c434605aefdbc7c`.

The final candidate version is `0.5.4rc4`. A version change grants no release
qualification. Its exact source must pass hosted checks; one fixed Linux
installer then needs the original offline workflow, recovery, native handoff,
four-prior replacement, cold-install, notices and independent authorization
gates. RC versions do not publish automatically. The physical app and real
workspace remain closed and untouched. No score is increased by source tests.


### Accepted cancellation correction and composed source replay

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


### 2 October: actual installed workflow diagnostic mismatch

The exact `791c9d87beee325d87f7090118b9600a4ba6eda6` Linux candidate
built successfully after the separate build-runner PATH correction. Its first
installed browser journey completed six named checks: package and desktop
identity, example discovery, exact handover originals, handover preparation and
save, and campaign action/draft save. The app then quit through its interface
with exit 0, no termination signal or forced cleanup, and its listener closed.
This is a normal quit, not a product crash or a completed workflow qualification.

The qualification owner and verifier incorrectly required empty app stdout.
The actual product prints its exact local-workspace URL; the unchanged quit
notice is on stderr. The original failed owner, all streams, partial browser
receipt and screenshots remain retained. A later cleanup attempt also lacked
the fixed browser temporary-directory field, producing a separate `KeyError`.
Reopen, restore and the three Word exports did not complete in that attempt.
The old package remains held and is not relabelled as qualified.

The source correction binds the exact startup banner to the canonical opener
and typed, actually admitted listener in both producer and original verifier.
It rejects missing, changed or extra output and keeps the exact stderr notice.
The owned temporary directory is recorded before the browser collector starts.
Cache cleanup still defaults to a normally stopped successful collector; only
an explicit, fully captured exit-1 collector after a retained original failure
may use the failure-cleanup path. Process ownership, complete streams, no forced
cleanup and the finite cache inventory remain required. Failure stays failure.

The author retained an initial inert-fixture shape failure, corrected that
fixture and passed 284 final focused SOURCE tests with zero failures, errors or
skips, plus required lint, changed-file formatting, Python 3.10 syntax and public
boundary checks. These are source checks only. A new exact-source hosted run,
new build, independent review and complete installed/recovery/upgrade journeys
are still required before RC4 publication. No provider call, real campaign edit
or higher product rating follows from this correction.


### 2 October: final quit decision in the following installed attempt

The following exact `af5c40ad1902ad36dea3750063484721af40afc9` candidate
built successfully. Its installed browser attempt retained 13 named checks
through reopening, backup restoration and preservation of originals. Five
screenshots, both backups and the handover/Word-copy files are retained. The
first app quit normally; the final stopped-state observation timed out. The
complete attempt failed in 50.23 seconds and remains failed. No final Word-copy,
second-normal-exit or release qualification is inferred from those partial files.

Source inspection found that the Word-copy exercise intentionally applies changed
report wording without saving that report. The product keeps that unsaved draft
across navigation and asks for an on-page **Quit Sinter?** decision. The old test
clicked only the toolbar and handled browser-native dialogs. An unanswered
on-page decision is the supported causal inference; no post-click DOM snapshot
or quit-request trace was retained. The later invalid-controller-transition
failure followed the host's timeout cleanup. The second app's normal exit is
unproven. This disposable test failure is separate from the user's normal close.

The correction selects the exact source confirmation profile and explicitly
answers only the matching modern dialog before checking the unchanged actual
exit/listener requirements. Older preview dialog handling remains intact;
unknown or mixed controls refuse. Twelve focused regressions cover profile
selection, consent ordering, missing decisions and non-normal exit observations.
The four relevant Python modules pass 362 tests. These are source regressions;
successor hosted, installed, recovery, upgrade and release gates remain pending.
The physical workspace and actual campaign data stay closed and untouched, with
no provider calls or change to the product ratings.


### 2 October: hosted Windows suite budget and timing evidence

Exact source `c4534142661c4fd78f5a4fcd172946a100e66627` hosted Quality
run `37005985832`, attempt 1, was cancelled. The original check annotation
states that the Windows Python 3.13 job exceeded its 12-minute execution limit.
Ten jobs succeeded; the source/portable job was skipped. This run is not green
and does not admit a native build or release. Its original logs and artifact
ZIP/XML bytes remain retained, including the later interruption teardown error.

The interrupted Windows 3.13 XML retains 4,605 of the expected 5,076 cases:
4,034 passed and 571 skipped, with no recorded failures or errors. Its suite
time is 711.679 seconds. The successful current Windows 3.10 suite took 582.324
seconds; the prior `af5c40a` Windows 3.13 suite took 409.790 seconds for 5,064
cases. Slow current cases are spread across qualification and campaign modules,
with the four slowest taking 15.679, 14.463, 14.184 and 12.058 seconds. The
interrupt happened while creating a local SQLite schema. These observations
show broad timing variation; they do not establish a deadlock or its cause.

The hosted Python job budget becomes 20 minutes, and its unchanged full Pytest
suite reports the slowest 25 tests. All matrix targets, assertions, correctness
checks, original XML uploads and downstream source dependencies remain required.
The time bound stays finite. This is qualification tooling only; it does not
change application behavior or raise product ratings. The successful portable
build for `c453414` remains mechanical evidence for that source, while its
cancelled hosted run and unexecuted installed proposals stay held. A successor
source requires its own hosted and original installed qualification.


### 2 October: browser identity acquisition in the next installed attempt

Exact source `959b9f65aabbb0a2f6f78b1731183b2a094e345b` passed all 12
hosted Quality jobs in run `37008571529`, attempt 1. Its original Linux native
build completed normally in 34.49 seconds. Independent mechanical review
verified the installer, native archive, binary, notices and original receipt.
Those observations establish packaging checks, not installed release acceptance.

The single installed workflow attempt failed in 16.85 seconds with
`Actual Chromium cmdline differs.` Its original browser row contains a complete
empty command record; the expected fixed command contains 12 arguments and 375
NUL-terminated bytes. The source reads `/proc/<pid>/cmdline` immediately after
starting Chromium, before waiting for its private debugger. The same PID later
appears in the browser process list, with a working debugger, normal exit 0,
complete streams and no termination signal or forced cleanup. A transient
startup observation is the supported inference; no later live command snapshot
was retained, so the precise kernel cause is unproven.

The UI producer retained all 22 named checks and 13 artifacts, including five
screenshots, both backups and four Word files. Both installed app lifetimes
quit through the interface with exit 0 and closed listeners. The complete owner
still failed its strict browser-identity check and remains failed. These partial
observations do not establish complete workflow, recovery, upgrade or release
qualification. The four unexecuted gate plans remain held; nothing is replayed.

The source correction moves one actual command read after validated private
debugger readiness and before connecting to the browser. It requires the exact
NUL-terminated command and a live process before and after reading. Empty or
changed observations still refuse, with no retry or expected-record fallback.
The final verifier, cleanup requirements and resource limits remain unchanged.
Successor source, hosted and installed gates are still required. The user's
normally closed app, real campaigns and provider allowance remain untouched.

The changed module passes 137 source tests, including 23 new injected identity
controls; those counts overlap. The literal earlier source fails the new ordering
test. Readiness timeout and malformed endpoints, wrong or truncated command
bytes, exit before or after the read, and read/cleanup faults are covered without
running a real browser. Required correctness lint, touched-file formatting,
Python 3.10 grammar for all 283 tracked Python files, the public-boundary check
and deterministic offline self-audit pass. These source checks do not replace a
new original installed run or qualify the held candidate.


### 3 October: same-observation socket admission

Exact source `a7159a54424209a8e111e1dbe66731e65eaf8136` hosted Quality
run `37016702815`, attempt 1, failed the macOS Python 3.13 cancellation fixture.
Its original XML contains 5,099 cases: 4,752 passed, 346 skipped, one failed and
zero errors. All 23 added browser-identity controls passed in that job. The
failed source is byte-identical to `959b9f6`; the original log, artifact and
recorded socket observations remain retained. This run does not admit a build.
The terminal run has ten successful jobs, the failed macOS job and a skipped
source/portable job. Windows Python 3.13 completed normally in 791.001 suite
seconds, within the 20-minute limit. No rerun or cancellation was used.

The failure occurred during fixture preparation, before a pending cancellation
was established. The test observed an actual zero-byte blocked fill, discarded
that call, then asserted that a separate fill would still accept zero bytes.
The later call accepted 65,536 bytes. The original production prefix was 4,096
bytes, the peer was neither read nor shut down, and cleanup completed. The
observations establish the test's invalid cross-call assumption; they do not
demonstrate a product cancellation failure. A socket's capacity can change
between observations even without a userspace peer read.

Two source reviewers agree on a narrow test correction: each bounded attempt
uses the intended active or inactive context from the start. The invocation
that actually observes zero additional bytes supplies the active admission or
propagates its original inactive refusal. A previous observation cannot stand
in for a later syscall. Real prefix, backpressure, cancellation, timeout and
cleanup requirements remain unchanged. Focused regressions and the successor's
hosted and original installed gates remain required before release acceptance.
The user's normal app close remains separate from this disposable test failure.

The changed cancellation module passes 54 tests, with zero skips and six
inherited JUnit-property warnings. Its 14-case focused selection overlaps that
total. Six new controls cover regained capacity and the existing attempt/time
bounds; the literal earlier branch fails all four capacity-regain cases. The
initial author run's one failure remains retained: an earlier acceptance flag
leaked into the later negative observation. Each current trial now replaces
that observation without synthesizing the flag; historical trials remain
separate. These checks are source evidence, not a macOS or installed-app pass.
Required correctness lint, touched-file formatting, Python 3.10 grammar for all
283 tracked Python files, the public-boundary check and the deterministic
offline self-audit pass. The audit records zero network requests.

### 3 October: browser cleanup record integration

Exact source `f4dc483187059051c6609d81d9abc72b50cedc74` hosted Quality
run `37022178214`, attempt 1, completed all twelve jobs successfully. Its
original portable and native builds completed, and their mechanical source,
package and dependency checks passed. These observations do not qualify the
complete installed workflow or admit publication.

The one original installed workflow failed with `Actual host browser/temp
boundary changed.` Its browser receipt reported 22 interface checks and both
app lifetimes quit normally with closed listeners. The final generic interface
verifier was not reached. The whole workflow remains failed; four later gate
plans were not executed. The original record and partial outputs remain intact.

The shared cleaner records `temporary_directory` and `temporary_cleanup` as
side effects and returns no value. The workflow had added `cleanup: null` from
that return while the verifier required a legacy six-field record. The source
correction invokes the cleaner for its side effects and requires the exact
seven-field boundary, fixed root/t path, existing 55-byte UTF-8 limit, an actual
empty directory without a symlink, unchanged browser identity and the existing
typed cleanup validator. Legacy and failed eight-field aliases still refuse.
No lifecycle, first-failure, resource, deadline or cleanup requirement is removed.

The affected module passes 163 unique source tests with no failures, errors or
skips on Linux. The separate 27-case selection overlaps that count. An exact
projection of the old branch fails the valid seven-field control as expected.
Twenty-six new cases cover identity, aliases, typed flags, cleanup, actual
directory state and Unicode/exact byte bounds. Independent source review
accepts the narrow three-path correction; it does not replay or rehabilitate
the failed installed result. Fresh exact-source hosted, build and original
installed qualification remain required. The user's normally closed app and
real saved workspace remain untouched.

### 3 October: recorded dates in campaign exports

The current interface preserves a recorded closing date when the application
window is unknown. Both campaign export forms now do the same, with the explicit
label `current window unverified`. This changes two presentation branches only;
the date does not establish a current window, urgency or eligibility. Original
source quotes, changed or stale snapshots, historical route status and saved
campaign bytes remain intact.

The campaign module passes 226 unique Python cases. Fourteen focused cases
overlap that total. Seven Node 22 cases pass, including the existing six
interface controls and a policy matrix for past/future dates and source changes.
The literal earlier label fails its expected control. The initial Node 18 ESM
loading failure and inherited import-order warnings remain recorded separately.
Independent byte and complete production AST review accepts the exact three-path
patch; it does not establish installed or release qualification. The user's
normal app closure remains separate from every disposable test run.

### 3 October: reviewed local handover opening

The optional source-only handover editor compiles explicit user wording with
literal subspans of the saved report's retained evidence. Original source hashes,
Unicode offsets, citations, inputs and review status remain unchanged. Unknown
and unassigned owners, unconfirmed acceptance and dates, missing evidence and
historical wording stay distinct. A stale report adds a visible review notice;
that source control does not claim an actual stale-report browser exercise.
Compilation does not contact a provider. Replacement of existing document edits
requires explicit approval and refuses changed report or draft snapshots.

Twenty-six distinct Node controls and three Python storage/Word controls pass.
The Python wrapper for those Node controls was excluded from that count. Eight
static source checks pass. The initial stale-fixture setup failure remains
recorded; independent review accepts the exact eight source paths.

A root-operated browser prototype used committed `9469cce` plus those exact
eight paths and a copied fictional workspace. The prior five-item saved report
reopened intact. Two new items exercised missing evidence, unknown/unassigned
owners and a literal retained sentence. Add focused the new item, collapsed the
earlier card and restored deliberately chosen card states after navigation.
Save and My workspace correctly called unapplied rows session-only. Cancelled
discard, quit and replacement preserved work. View-only toggles retained the
preview; changed wording required a new preview. Explicit replacement, save and
reopen preserved the two items and original evidence. A distinct Word copy was
saved; the temporary app quit normally and its only owned tab was closed.

At 540 pixels the summary table uses readable wrapping and a focusable horizontal
scroll container. Keyboard scrolling exposed the Evidence column. The regular
two-item opening was visually inspected. The earlier five-item Word opening
spans two pages and remains a material formatting limitation. Structured rows
remain session-only until applied; they are saved as ordinary document text.
These source and fictional interface observations do not qualify an installed
package, a customer platform, an AI task or a whole-product 10/10 rating. The
failed earlier installed workflow remains failed; fresh qualification is required.

### 3 October: Unicode recovery and scoped Word layout

Exact source `dcf9085277b3efa4d98320124b76547a42c3ae5c` hosted Quality
run `37038957852`, attempt 1, ended with eight successful jobs, three failed
jobs and one skipped job. Chromium expected an earlier unsaved-edit sentence;
both Windows versions found zero Word bookmarks where eight were required.
The packaging job was skipped. The original complete logs and artifacts remain
retained; neither that source nor its installed release is qualified.

The browser correction requires the current exact save notice, the visible newer
wording, absence of the older submitted text in the editor and the actual older
snapshot in local storage. Its nine private offline browser journeys pass with
no external requests. The dirty-exit and further-save controls remain active.
Independent source review accepts this stronger check without replaying CI.

The handover test bridge now decodes actual Node stdout and stderr as strict
UTF-8. The same raw fixture decoded as UTF-8 retains eight bookmarks and 22
links; a legacy Windows encoding loses both while earlier ASCII and table
checks still pass. This supports an encoding diagnosis; the original Windows
locale was not measured. Seven source cases pass, including real Unicode pipe
output and refusal of invalid bytes. The original navigation requirements and
complete fixture fields remain unchanged. The initial author assertion error
and the literal old helper's expected failure remain separate records. Fresh
Windows CI is required before a platform claim.

Word export applies fixed column widths only to the exact generated, top-level
reviewed opening. Changed, quoted, nested or ambiguous shapes retain the generic
layout. Sixty-seven source cases pass. Exact comparison preserves all wording,
Unicode spans, fonts, source identities, bookmarks, links, package parts and the
original quoted action table; only the first table's layout properties change.
Independent source review accepts that narrow presentation change.

The original five-item browser-created payload reproduces its earlier Word copy.
Its new headless LibreOffice render puts all five complete rows on page one;
the whole document still has five pages. Root and an independent reader inspected
every rendered page. Passage 3's source caption is separated from its table, and
the final reference remains alone on page five. These remain formatting work.
Root opened the exact read-only copy in a separate native LibreOffice profile,
observed its five-page status and first-page table, and quit normally with exit 0.
Native keyboard page navigation was refused by the desktop portal and was not
replayed. This is source-document evidence, not installed Sinter, Microsoft Word,
customer-platform, whole-product quality or release qualification. The user's
normally closed Sinter and real saved workspace remain untouched.

The root-composed source passes all 74 affected Python cases without failures,
errors or skips. Required correctness lint, touched-file formatting, public
boundary checks and Python 3.10 grammar for all 286 Python paths pass. The
deterministic local self-audit records no network requests. These checks do
not substitute for the fresh exact-source hosted and installed gates.

### 3 October: actual cross-version pipe boundary

Successor `f9de1db12fe22521485d0600bddeb208679e6825` hosted Quality
run `37043622354`, attempt 1, ended with seven successful jobs, four failed
jobs and one skipped job. Its original 5,172 cases per platform, complete logs,
warnings and artifacts remain retained. All six platforms passed the original
eight-bookmark/22-link Word check and the 19 scoped-layout cases. Packaging
was skipped; this whole source qualification remains failed.

The new positive regression assumed a private Python helper that is absent
in 3.10. Both Windows versions also emitted the intended invalid byte, but
their subprocess reader threads raised the decoding exception without passing
it to the caller. The original warnings contain the exact `0xff` byte; they
were not suppressed or treated as successful caller validation.

The source-test helper now captures actual bytes and decodes both channels as
strict UTF-8 on the calling thread. The positive case runs the exact helper in
a real Python child with UTF-8 mode and locale coercion disabled, recording the
observed codec rather than patching private internals. Both invalid-channel
cases require the caller's exception to retain the original byte. All four
original scenarios and the fixture, storage and navigation checks remain intact.
Seven source cases pass; the literal earlier decoder fails as expected.

A separate cached, network-free container exercised the actual boundary once
with Python 3.10.12 and an observed ASCII locale. Unicode remained exact, both
invalid channels reached the caller, and the original default decoder failed
on the real Unicode bytes. Complete streams, normal exit, container removal,
full-ID absence and unchanged inputs/image were retained. This proves that
source boundary; it does not replace the complete fresh Python 3.10, Windows,
installed-app or release qualification. The unexecuted earlier build plans
remain held, and the user's closed workspace remains untouched.

The reconciled source also retains the independently pushed public `Popen`
ANSI-default simulation and its real-pipe control. Both positive paths run,
with the stronger original-byte checks on each invalid channel. The remote
macOS 15 runner update is retained. Fresh hosted checks must qualify this
combined source; no prior result is promoted to it.

### 3 October: installed startup identity acquisition

Exact source `42ea64a8e723240b2b26f3e3af7ed45ed9ddcd13` completed all
twelve jobs in hosted Quality run `37084753205`, attempt 1. The original
portable and native builds passed their mechanical checks. These observations
did not qualify the installed release.

Its one original installed workflow failed with `Actual app cmdline differs.`
The second launch retained an empty process-command snapshot; the first retained
the exact 73-byte command. Both launches later quit through the interface with
exit 0, complete streams, closed listeners and absent process groups. The browser
producer reported 22 checks passing, but the owner remained failed and the final
generic interface verifier was not reached. Four later gate plans were not run.
The failed records and partial outputs remain intact.

The producer had sampled identity immediately after process creation, before
bounded opener readiness. The correction takes one complete snapshot after the
validated opener, with a live-process check before and after, and immediately
requires the exact NUL-delimited command before publishing running state. It
does not retry an empty reading, substitute expected bytes, relax the final
verifier or change the startup limit, lifecycle or cleanup requirements. Fresh
exact-source hosted, build and installed qualification remain required. The
user's normally closed app and saved workspace remain untouched.

The affected module passes 187 source cases with no failures, errors or skips,
including 24 new controls for readiness ordering, malformed or missing openers,
early process exit, exact original command bytes, read failures and independent
cleanup. The initial 23-case selection overlaps that total. Correctness lint,
touched-file formatting and Python 3.10 grammar pass. These injected controls
do not substitute for an actual installed run.
