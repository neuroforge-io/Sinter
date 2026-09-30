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

On the final development bytes, the full Python suite passed **1,939 tests with
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
