# Sinter user-testing closeout — 12 September 2026

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
