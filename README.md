<div align="center">

# Sinter
### Less busywork. More community.

**A free, open-source workbench for the people doing the work.**

Fragmented knowledge. Funding research. Clear correspondence. Reviewable meeting records.<br>
Action plans and shared knowledge, with the evidence still in view.

[Download Sinter](https://github.com/neuroforge-io/Sinter/releases) · [Getting started](docs/INSTALLATION.md) · [What you can do](docs/WORKFLOWS.md) · [Help & feedback](https://github.com/neuroforge-io/Sinter/issues)

**Apache 2.0 · Local-first · Linux preview · By NeuroForge**

</div>

---

## Current preview: 0.5.4rc3

The [Linux x64 preview is published](https://github.com/neuroforge-io/Sinter/releases/tag/v0.5.4rc3),
qualified on Ubuntu 22.04/glibc 2.35. Other platforms are not qualified for this
preview. [Publication evidence](docs/releases/PREVIEW_0.5.4rc3_PUBLICATION_RECEIPT.md)
records the exact public downloads and installed/upgrade scope.

The package source is frozen at `246b91e0ee432cb1f6f6fcd17425f55cd7a4cabe`.
Later `main` commits do not change those downloads. Twenty-one installed browser
checks cover the paired garden example, source inspection, edited handover and
actions, save/quit/reopen, actual Word copies and separate restored backups.
Additional installed recovery covers held actions and a stopped-server backup.
Separate copied-workspace and actual package upgrades from v0.5.3, RC1 and RC2
retain fictional work, preferences and explicit model selections. No model
operation was requested by these checks.

The app defaults to a smaller native **source workspace**. For funding campaigns,
rich documents and account sign-in, open the full browser workbench with
`/opt/neuroforge/sinter/Sinter app --mode browser` after installing the Debian
package. Its Overview offers **Open garden handover** and **Open garden campaign**.
See [one portable runtime](docs/PORTABLE_RUNTIME.md) for the separate presentations.
Native qualification covers repeat launch and clean shutdown; full native editing
and customer-device acceptance remain unqualified.

Linux Python and Chromium CI passed. The aggregate cross-platform Quality run
failed: Windows test-fixture portability and a genuine macOS concurrent Word-save
failure remain open. The release page retains these limits; this is a Linux-only
preview, not a cross-platform qualification or a whole-product 10/10 claim.

The earlier v0.5.3, [v0.5.4rc1](docs/PREVIEW_0.5.4rc1.md) and
[v0.5.4rc2](docs/PREVIEW_0.5.4rc2.md) previews remain
unchanged; their installers have different source and capabilities.
See [preview scope and evidence](docs/releases/PREVIEW_0.5.4rc3_PUBLICATION_RECEIPT.md)
before choosing an asset.
Start with the [fictional offline garden walkthrough](examples/offline-garden/README.md).
It needs no account, internet, model download or hosted generation.

### Clearer work and safer recovery

Research now has a dedicated brief: source highlights, clickable citations, focus
questions and gaps to investigate. **Find a tool** (`Ctrl+K` or `⌘K`) takes you straight
to the work you need. Completed forms fold away, reports show evidence counts, and
every example runs locally with accurate fictional labels.

The `sinter` command now prints help when run without arguments; `sinter serve`
opens the workbench. Reviews can discover a matching checkpoint or use an explicit
`--checkpoint`, retain useful grounded prose findings and explain the next recovery
step. Template steps keep their source context, preserve incomplete output and never
silently replay a request. Funding campaigns keep opportunities, quotes and next
actions in a revisioned local record. Readable drafts can be edited and exported
to Word while their original sources remain in the evidence pack.

Current development shows compact quoted-cost rows and opens the next missing
price or reference. Open and closed cost rows stay as left when moving between
pages in the same browser session. Quoted subtotals retain original amounts, unknowns and GST
wording; they do not establish an application amount or funding-ceiling decision.
The campaign workbench marks current application answers for review when active
costs change. Direct CLI/Python saves retain entered review statuses; review them
explicitly after changing costs.
[Budget meanings and recovery](docs/CAMPAIGN_BUDGETS.md) explains this boundary;
reviewed application-amount entry remains an
[open extension](docs/APPLICATION_BUDGET_V2_DESIGN.md).

New connections discover the current supported NeuroForge model. Saved explicit
choices are preserved. Answers start at 64 tokens; automatic/dense requests are
capped to the advertised profile: native ERAIS 128, dense 512, hybrid up to 2,048.
Native requests use one JSON response, even when the interface displays a stream.
For native ERAIS, choose **Explore AI → Multi-step templates → Short source answer**
and preview the exact selected excerpt and question before sending. Full reviews,
long letters and eligibility decisions do not fit this small profile; Sinter
retains those inputs and asks for a smaller scope or an explicitly capable provider.
See the [native API contract and fixtures](docs/NATIVE_API_COMPATIBILITY.md).
One hosted generation runs at a time in each Sinter process, with
bounded, cancellable waiting. Install the new package to receive these changes;
existing installations do not update themselves.

[Testing findings and validation](docs/QUALITY_REVIEW_2026-09-12.md)

### Choose your optional assistant

Settings offers NeuroForge's keyless preview, ChatGPT account access, Anthropic,
OpenAI API keys, Gemini and compatible local or remote model servers. Load the
model list before saving, or enter an exact model identifier. A successful model
check confirms discovery; it does not claim that generation has been tested.
Search continues through NeuroForge when another model provider is selected.

ChatGPT plan access uses OpenAI's documented sign-in flow for eligible users and
qualifying open-source local applications. Source installations need the optional
account verification package: `python -m pip install 'sinter[accounts]'` (from a
checkout, use `python -m pip install '.[accounts]'`). The provider controls response
length and plan limits. Account tokens stay in protected local account storage;
API keys entered for other providers stay in memory for the session. Sign-in alone
does not change the selected model connection. See
[OpenAI's account access guide](https://developers.openai.com/siwc/token-sharing-open-source/sign-in).
Set an app allowance in ChatGPT's **Settings → Usage → App limits → Sinter** if
you want a weekly ceiling, and leave credit fallback off to stay within that plan
allowance. Sinter does not infer a remaining plan percentage from token counts.

In Explore AI, the campaign assistant helps prioritise next actions, explain
eligibility gaps or draft an enquiry. Select a saved route and the checks to
include, inspect the context, then approve the model request. Suggestions stay
separate from campaign records. Changes to the campaign invalidate an earlier
preview. No messages or applications are sent by this assistant.

[Optional assistant testing and limits](docs/ASSISTANT_VALIDATION_2026-09-30.md)

### Review quality and current recovery behaviour

Collection review now shapes batches from a deterministic local analysis: each batch
is cut at statement and line boundaries and asked targeted questions about the real
symbols, imports and risk-shaped lines in its own excerpt. A received but unsupported
answer is recorded as a defined partial batch that an explicit resume may re-review
with a bounded follow-up question. Coverage reports partials separately and returns
exit code 3 when follow-up is needed; failed or uncertain provider outcomes and
runtime validation errors return 1. Missing arguments or invalid command syntax
return 2. The native ERAIS preview refuses full collection review before generation
or checkpoint changes; offline coverage planning remains available. Checkpoints
embed the review engine so older plans are rejected cleanly.

## Reliability update: 0.5.1

Collection review now writes a checkpoint before each remote request, preserves
uncertain outcomes without silently replaying them, and separates completed,
failed, uncertain and unattempted coverage. Intake includes CI/configuration and
extensionless UTF-8 text with bounded admission and original-byte hashes. Evidence
selection no longer substitutes unrelated excerpts when wording overlap is absent.
See the [changelog](CHANGELOG.md) and [recovery guide](docs/LARGE_REVIEWS.md).

## New in 0.5: put the fragments together

**Community casebooks** bring notes, replies, policies and past work into one local,
revisioned project. Ask your questions, keep the original wording, and prepare a
briefing, enquiry, agenda item or volunteer handover with explicit coverage and gaps.
Optional AI drafting uses a previewed excerpt pack, never a silent upload of the collection.

In the rc3 browser workbench, **Choose sources for each question** limits related-wording
matches to your explicit selections. Choosing none leaves that question unanswered;
all original inputs remain in the project backup. Changing questions or removing
selected sources requires reviewing those choices. Scoped projects use casebook v2:
older previews cannot show them or restore their backups. Keep a separate workspace
copy before switching versions.

**Recent activity** recovers results after a lost browser connection. **Bounded reviews**
process large text collections in small batches with checkpoints and an honest coverage
ledger. Completed work is retained when a later batch fails; generation is never
automatically replayed.

[Casebook guide](docs/CASEBOOKS.md) · [Large reviews and recovery](docs/LARGE_REVIEWS.md)

## Start with something useful

Sinter is for P&Cs, clubs, associations, volunteer teams and anyone who has more useful work than spare time. It combines small, dependable local tools with optional assistance from the **NeuroForge API**. You do not need to learn prompt engineering to begin.

| Bring this | Make this | Keep this visible |
| --- | --- | --- |
| An organisation profile and funding questions | A source-linked funding shortlist, requirement checks and recurring searches | Missing conditions, source dates and eligibility uncertainty |
| Notes, references and questions | An enquiry letter, briefing note or agenda item | Original excerpts and unanswered questions |
| A meeting transcript or recording* | A reviewed transcript and draft minutes | Speaker labels, original wording, corrections and review flags |
| Tasks and proposed dates | An action plan, volunteer handover or event checklist | Owner type, accepted responsibility and unconfirmed timing |
| Two document versions | A line-by-line wording comparison | Exactly which lines changed, not an AI judgement of their meaning |
| An exported RKC atlas | A cited source packet and optional model-assisted draft | Snapshot identity, source paths and citation identifiers |

\* Recording transcription requires the optional speech-enabled **source installation**. Core desktop installers support transcript import and review without downloading a speech model.

### A workspace that feels like yours

Choose dark or light appearance, larger reading text, comfortable or compact layouts and reduced motion. Projects have clear inputs, visible progress and reviewable outputs. Work can be exported rather than locked into a service.

The installed application includes Python and opens a native source workspace.
The full browser workbench currently requires the explicit command below.
The fictional examples need no account, personal data, internet or model download.

## Install, open, try an example

1. Open the [0.5.4rc3 release](https://github.com/neuroforge-io/Sinter/releases/tag/v0.5.4rc3) and choose its Linux x64 package if your environment matches the tested Ubuntu 22.04/glibc 2.35 baseline.
2. Run the installer using your normal operating-system software controls.
3. For the full campaign walkthrough, run `/opt/neuroforge/sinter/Sinter app --mode browser`, then choose **Open garden campaign** or **Open garden handover** from Overview. The application-menu entry opens the smaller native source workspace.

| System | Current 0.5.4rc3 availability | Qualification |
| --- | --- | --- |
| Ubuntu Linux, Intel/AMD 64-bit (`x64`) | `.deb` installer and native `.tar.gz` runtime | Ubuntu 22.04 / glibc 2.35 installed and upgrade tests |
| Windows, macOS and other Linux architectures | No qualified rc3 installer | Earlier previews remain on Releases; they do not contain rc3 changes |
| Source / portable Python app | Source ZIP and `sinter.pyz` | Requires Python 3.10+; qualification is limited to Linux in this preview |

**These are community preview builds, not publisher-signed or notarised installers.** Operating-system policy may warn or block installation. Follow your organisation's software policy; do not disable security protections. Build receipts record the interpreter, processor, compatibility/emulation mode and installed-app tests. A passing build is not certification for every older OS version.

`x64` covers both AMD and Intel processors. Other distributions and older runtime
combinations have not been qualified for rc3. See
[installation details and limitations](docs/INSTALLATION.md).

### Prefer source?

```sh
git clone https://github.com/neuroforge-io/Sinter.git
cd Sinter
python3 start.py
```

On Windows use `py start.py`, or double-click `Start-Sinter.bat`. The source launchers prefer the project's `.venv` when it exists. To update a clean checkout: `git pull --ff-only`, then restart.

## Practical tools, not just a chat window

**Funding discovery and watches.** Search using the question you choose, retain source excerpts, and compare human-confirmed requirements with an organisation profile. Watches preserve results across restarts and show new, changed or not-returned results. You can pause them and export calendar reminders. Checks run only while Sinter is open; search absence does not prove a grant has closed.

**Briefs, letters and agenda items.** The evidence workbench uses original excerpts and restrained document structures. Optional source ranking can select known excerpts; it cannot invent factual prose inside source-only reports. Use the separate generative templates for a richer draft, then review it against the originals.

**Community plans.** Record actions, owners, confirmed dates and progress. Export CSV, JSON and calendar files, or save the plan in My workspace. The comparison tool finds changed lines in earlier and updated wording. Line-ending styles and the final newline are intentionally ignored.

**Eight community drafting recipes.** Enquiry letters, agenda items, action registers, grant preparation, volunteer handovers, event plans, newsletters and consultation questions. Each keeps the original context available across extraction, drafting and review stages. A model self-check is not independent verification.

[Read the workflow guide](docs/WORKFLOWS.md).

## Meeting audio: listen, review, keep the original

The optional local recognition workflow supports language selection, word timings, uncertain-passage flags, recording hashes, local playback and paginated review. Human speaker labels retain their original values. Corrections do not erase the original transcript, and review flags carry into minutes.

Install the optional engine in a source checkout:

```sh
python3 setup_speech.py
# Windows: py setup_speech.py
```

The helper asks before installing packages into `.venv`. Model-download permission is separate. Audio processing remains local. Exports include JSON, TXT, SRT and VTT; JSON retains the detailed recognition metadata.

**Isolated microphone channels can be transcribed separately. A mixed room recording is not automatically diarised, and voices are not automatically identified.** Names, numbers, negation and unclear passages need a person to listen and confirm. Short speech integration tests do not establish accuracy on long, noisy community meetings.

[Speech setup, supported inputs and review guide](docs/TRANSCRIPTION.md).

## Optional RKC knowledge connection

[RKC](https://github.com/neuroforge-io/RKC) is NeuroForge's open-source Repository Knowledge Compiler. Sinter can import an atlas, request cited context from its local HTTP service, and invoke an explicitly selected RKC executable to compile selected text files into a new atlas.

Model assistance works **beside** RKC: Sinter sends a bounded, approved excerpt pack to its configured API and labels the result an unverified draft. It does not rewrite canonical atlas evidence or qualify a provider inside RKC's own model-execution system. Compilation does not need a language model.

[Connect an atlas and understand the boundary](docs/ATLAS.md).

## Your data and the public service

| Operation | Where data goes |
| --- | --- |
| Local examples, deterministic reports, plans, comparisons and atlas imports | Your computer |
| Explicitly saved reports, watches and preferences | `~/.sinter`, or `SINTER_DATA_DIR`; not encrypted |
| Search and recurring search watches | The exact query goes to NeuroForge’s search API |
| Optional ranking, generative templates, chat or atlas drafting | The selected question/context goes to your configured API |
| Optional speech recognition | Audio remains local; authorised model downloads contact the model host |
| Session key entered in Settings | Process memory only; not saved into preferences or exports |

The default NeuroForge service is a public preview with capacity and availability limits, **not a 24/7 service guarantee**. Its selected backend may be native ERAIS, dense or legacy Fracture. Native ERAIS is explicitly unqualified for general chat; protocol admission does not establish answer quality. A dense response is not a sparse conversion result. Sinter itself is free; a different provider or private deployment can have its own terms and charges. Advanced connection settings are optional, and changing the destination requires confirmation.

Exact quotations establish provenance, not truth, authority, currency or completeness. Sinter never sends official letters, approves minutes or submits grant applications automatically. The local server is for one trusted local user, not an internet-facing team service.

## Open to improvement

The core uses Python's standard library and modular browser-native HTML, CSS and JavaScript. Native packages bundle a runtime rather than a second browser engine. Tests cover source provenance, HTTP boundaries, saved work, cancellation, user preferences, atlas handling, speech integration, browser journeys and installed-app execution.

[Development and tests](docs/DEVELOPMENT.md) · [Installer build details](docs/INSTALLATION.md) · [Boundaries and audit notes](SELF_AUDIT.md)

The public landing page lives in `site/`; the Pages workflow publishes only those static files. It lists actual release assets rather than guessing that an installer exists. See [deployment setup](docs/INSTALLATION.md#publishing-the-site).

## Licence and ownership

Sinter source remains **Apache 2.0**. Preserve the [LICENSE](LICENSE), [NOTICE](NOTICE) and applicable changed-file notices. No proprietary ERAIS/Fracture implementation or model weights are bundled. The API is an interface, not a redistribution of its server.

Bundled runtime components and optional packages/models retain their own licences. Read [third-party notices](THIRD_PARTY_NOTICES.md); an Apache-2.0 application does not relicense its dependencies or the material you import.

---

**Built by NeuroForge. Open to the community.**
