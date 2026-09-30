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
