<div align="center">

# Sinter
### Less busywork. More community.

**A free, open-source workbench for the people doing the work.**

Fragmented knowledge. Funding research. Clear correspondence. Reviewable meeting records.<br>
Action plans and shared knowledge, with the evidence still in view.

[Download Sinter](https://github.com/neuroforge-io/Sinter/releases) · [Getting started](docs/INSTALLATION.md) · [What you can do](docs/WORKFLOWS.md) · [Help & feedback](https://github.com/neuroforge-io/Sinter/issues)

**Apache 2.0 · Local-first · Windows / macOS / Linux · By NeuroForge**

</div>

---

## Reliability update: 0.5.2

Collection review now shapes batches from a deterministic local analysis: each batch
is cut at statement and line boundaries and asked targeted questions about the real
symbols, imports and risk-shaped lines in its own excerpt. A received but unsupported
answer is recorded as a defined partial batch that an explicit resume may re-review
with a bounded follow-up question. Coverage reports partials separately and returns
exit code 2 while any partial, failed or uncertain batch remains. Checkpoints embed
the review engine so older plans are rejected cleanly.

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

**Recent activity** recovers results after a lost browser connection. **Bounded reviews**
process large text collections in small batches with checkpoints and an honest coverage
ledger. Completed work is retained when a later batch fails; generation is never
automatically replayed.

[Casebook guide](docs/CASEBOOKS.md) · [Large reviews and recovery](docs/LARGE_REVIEWS.md)

## Start with something useful

Sinter is for P&Cs, clubs, associations, volunteer teams and anyone who has more useful work than spare time. It combines small, dependable local tools with optional assistance from the **NeuroForge Fracture API**. You do not need to learn prompt engineering to begin.

| Bring this | Make this | Keep this visible |
| --- | --- | --- |
| An organisation profile and funding questions | A source-linked funding shortlist, requirement checks and recurring searches | Missing conditions, source dates and eligibility uncertainty |
| Notes, references and questions | An enquiry letter, briefing note or agenda item | Original excerpts and unanswered questions |
| A meeting transcript or recording* | A reviewed transcript and draft minutes | Speaker labels, original wording, corrections and review flags |
| Tasks and confirmed dates | An action plan, volunteer handover or event checklist | Stated owners and commitments, rather than invented ones |
| Two document versions | A line-by-line wording comparison | Exactly which lines changed, not an AI judgement of their meaning |
| An exported RKC atlas | A cited source packet and optional Fracture-assisted draft | Snapshot identity, source paths and citation identifiers |

\* Recording transcription requires the optional speech-enabled **source installation**. Core desktop installers support transcript import and review without downloading a speech model.

### A workspace that feels like yours

Choose dark or light appearance, larger reading text, comfortable or compact layouts and reduced motion. Projects have clear inputs, visible progress and reviewable outputs. Work can be exported rather than locked into a service.

The installed application opens its interface in your existing browser. It includes Python: **the core installers do not require a terminal, Git, Python installation or an account**. Choose **Try an example** for a fictional, offline first run. No personal data or API key is needed for the examples.

## Install, open, try an example

1. Open [Releases](https://github.com/neuroforge-io/Sinter/releases) and choose the package for your operating system and processor.
2. Run the installer using your normal operating-system software controls.
3. Open **Sinter** from your applications menu and choose **Try an example**.

| System | Packages | Architecture choices |
| --- | --- | --- |
| Windows | Per-user `.exe` installer, shortcuts and uninstaller | Intel/AMD 64-bit (`x64`), 32-bit (`x86`), ARM64 |
| macOS | `.pkg` installing `Sinter.app` in Applications | Apple Silicon (`arm64`), Intel 64-bit (`x64`) |
| Debian / Ubuntu Linux | `.deb`, plus a portable runtime archive | Intel/AMD `x64` and `x86`, ARM64, ARMv7 (`armhf`) |
| Other supported source environments | Source ZIP, wheel or `sinter.pyz` | Python 3.10 or newer; no third-party core runtime packages |

**These are community preview builds, not publisher-signed or notarised installers.** Operating-system policy may warn or block installation. Follow your organisation's software policy; do not disable security protections. Build receipts record the interpreter, processor, compatibility/emulation mode and installed-app tests. A passing build is not certification for every older OS version.

Modern macOS has no 32-bit target here. `x64` covers both AMD and Intel processors. ARMv7 runs are tested under emulation, and x86 packages in a 32-bit compatibility environment. Linux packages record their minimum glibc version. See [installation details and limitations](docs/INSTALLATION.md).

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

Fracture assistance works **beside** RKC: Sinter sends a bounded, approved excerpt pack to its configured API and labels the result an unverified draft. It does not rewrite canonical atlas evidence or declare Fracture a qualified provider inside RKC's own model-execution system. Compilation does not need a language model.

[Connect an atlas and understand the boundary](docs/ATLAS.md).

## Your data and the public service

| Operation | Where data goes |
| --- | --- |
| Local examples, deterministic reports, plans, comparisons and atlas imports | Your computer |
| Explicitly saved reports, watches and preferences | `~/.sinter`, or `SINTER_DATA_DIR`; not encrypted |
| Search and recurring search watches | The exact query goes to your configured search API |
| Optional ranking, generative templates, chat or atlas drafting | The selected question/context goes to your configured API |
| Optional speech recognition | Audio remains local; authorised model downloads contact the model host |
| Session key entered in Settings | Process memory only; not saved into preferences or exports |

The default Fracture service is a public preview with capacity and availability limits, **not a 24/7 service guarantee**. Sinter itself is free; a different provider or private deployment can have its own terms and charges. Advanced connection settings are optional, and changing the destination requires confirmation.

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
