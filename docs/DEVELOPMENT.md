# Development and configuration

[Back to Sinter](../README.md)

## Install and test

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install '.[dev,browser,accounts]'
python -m pytest -q
python -m ruff check --select E9,F63,F7,F82 src tests tools
python tools/check_public_boundary.py
python tools/build_zipapp.py
python dist/sinter.pyz --version
python -m playwright install chromium
python tools/browser_smoke.py
python tools/deliverable_browser.py
python tools/campaign_browser.py
python tools/campaign_hold_browser.py
python tools/campaign_backup_browser.py
python tools/campaign_source_picker_browser.py
python tools/campaign_currency_browser.py
python tools/campaign_action_bar_browser.py
python tools/communication_view_browser.py
python tools/campaign_guidance_browser.py
python tools/handover_appendix_browser.py
python tools/casebook_save_state_browser.py
python tools/casebook_context_browser.py
python tools/casebook_question_evidence_browser.py
python tools/casebook_confirm_browser.py
python tools/quit_browser.py
python tools/document_export_browser.py
python tools/download_lifecycle_browser.py
python tools/document_page_break_browser.py
python tools/quality_browser.py
```

The setup above includes account-verification tests on supported crypto targets.
On Intel macOS, install `.[dev,browser]` and use a supported environment for the
signed account tests.

Windows activation: `.venv\Scripts\activate`. Browser integration uses fictional local fixtures and a temporary workspace. It must run in an environment that permits a browser to access its local HTTP server; do not bypass managed browser policies. The Actions workflow provides such an environment.

Every browser integration tool accepts `--help` without Playwright installed.
The same setup runs `browser_smoke.py`, `studio_browser.py`, `desktop_browser.py`,
`casebook_browser.py`, `casebook_save_state_browser.py`,
`deliverable_browser.py`, `campaign_browser.py`,
`campaign_hold_browser.py`, `campaign_backup_browser.py`,
`campaign_source_picker_browser.py`,
`campaign_currency_browser.py`,
`campaign_action_bar_browser.py`,
`communication_view_browser.py`,
`campaign_guidance_browser.py`,
`handover_appendix_browser.py`, `document_export_browser.py`,
`download_lifecycle_browser.py`,
`document_page_break_browser.py`,
`quality_browser.py` and `site_browser.py`. Use `--chromium /path/to/chromium` or
`SINTER_CHROMIUM` for an existing browser; the command-line option takes priority.
Missing packages or browsers fail with installation guidance and a nonzero exit
status, so an unexecuted integration test cannot silently pass CI.

On Linux, keep Chromium's runtime temporary path short. A deeply nested `TMPDIR`
can exceed the Unix-socket path limit before any app test runs. Keep durable logs
in the private operation directory, use a separate short private runtime path,
and consolidate retained evidence after the owned browsers have closed. Do not
change browser security settings to work around a setup failure.

For `tools/report_recovery_browser.py`, set `SINTER_BROWSER_ARTIFACTS` to a
private absolute directory to keep its screenshots and receipt together with
operation logs while preserving earlier browser evidence. Its final restoration
image covers one viewport; the sidecar records image scope, DOM geometry and
capture success. Complete content and evidence checks run separately.

On a shared machine, keep local authoring, checks, builds and browser rehearsals
sequential. Use explicit CPU/memory limits, low scheduling priority, finite
deadlines and owned process handles. Persist intent before mutation; after an
observation timeout, inspect the same handle rather than starting a replacement.
Return resources as soon as the actual child is terminal. Keep one primary
checkout, close owned tabs and retire only verified disposable work.

Treat source transport as part of qualification. A transient service launcher
expanded JavaScript interpolation in an earlier authoring packet. Send an encoded
program/payload when a launcher may expand code arguments, and compare independent
expected byte lengths and SHA-256 hashes before writing, after atomic replacement,
and against staged/committed blobs and the pushed source. Hashing only the already
transported payload cannot detect that corruption.

In the recorded Node 22.23.1 environment, a file-only syntax check returned zero
for an ES module that an actual import rejected. Parse the exact bytes explicitly
as a module, and retain an invalid-input control before trusting that check:

```sh
node --input-type=module --check < src/sinter/web/workbench-draft-switcher.js
```

Module import and the relevant real browser journey remain separate requirements.
Browser failure receipts include bounded source locations; preserve failed
receipts and screenshots before changing a check or trying again.

For a repeatable local portfolio measurement, run
`python tools/campaign_portfolio_profile.py --chromium /path/to/chromium`.
It uses the same fictional 170,000-character fixture as the recorded baseline
and retains all 61 timings, setup failures and ten separate driver-overhead
samples in a fresh temporary evidence folder. Measurements include automation,
scrolling and assertions; no overhead is subtracted. Host load and customer
devices are uncontrolled. The tool checks the saved workflow and fixture
identity; it does not enforce a CI timing threshold or establish a speedup.

For a matched correspondence comparison, use the same
`tools/campaign_communications_profile.py` with `--source-root` pointing to each
exact source tree and a new `--output-dir` for every sequential A/B/B/A run.
The fixed fictional workload contains 47 messages, 76 sources and 12 routes.
The tool retains complete saved documents, every attempted timing, source and
harness hashes, failures and cleanup results. Its common controls work with the
older eager editor and the current lazy editor; it does not impose a speed target
or qualify an installed release. Keep unrelated builds and browser tests separate
from the comparison, and retain interrupted or failed runs before trying again.

Other integration and release tools also explain their arguments with `--help`:

```sh
python tools/rkc_smoke.py /path/to/rkc
python -m pip install pyinstaller==6.22.2 certifi '.[accounts]'
python tools/package_native.py --arch x64
python tools/release_manifest.py publish source-package
```

Build the pinned RKC revision in `.github/workflows/ci.yml` for the real RKC
check. Native packaging requires a matching target interpreter and builds,
installs and tests the package using the platform tools documented by
`.github/workflows/native.yml`. Release assembly requires `GITHUB_SHA` to be the
full 40-character source commit verified by CI, plus all nine matching installer
receipts and the verified source package. Setup errors exit with status 2;
release validation failures exit with status 1 and never waive missing receipts.

Signed account tests use local generated keys and mocked provider replies; they
never sign in to a real account. CI installs the accounts extra on supported
crypto targets and still tests the explicit missing-extra path. On Intel macOS,
run core tests without that extra or use a supported environment for account
tests. Current cryptography no longer supports Intel macOS or 32-bit Windows;
its Windows ARM64 wheels are also unavailable. Native builds on those targets
use `--without-accounts` and explicitly exclude the verifier packages. No older
crypto release is substituted silently.

Supported native account builds collect PyJWT, cryptography and their runtime
metadata explicitly. Frozen and installed self-tests sign and verify an offline
RS256 fixture through Sinter's identity-verification path and reject an invalid
signature. Release assembly checks that target's capability, dependency versions,
licence inventory and test receipt. Linux x86 builds use Debian Trixie's current
Rust compiler for cryptography's source build; ARMv7 uses the supported wheel in
Bookworm. Cross-platform success remains subject to the actual CI receipts.

Published native receipts preserve both `frozen_test` and `installed_test`.
Their version, platform, interpreter, pointer size and account capability must
match; the published runtime checks come from the actual installed executable.
Release assembly rejects missing or mismatched installed proof.

Optional real speech integration downloads short test audio from a pinned revision of the upstream faster-whisper tests, and a tiny model from its normal model host. No personal recording, repository secret or Fracture API key is used:

```sh
python -m pip install '.[speech]'
python tools/speech_smoke.py
```

The test prints and retains an explicit receipt. It is a bounded interoperability check, not a meeting accuracy benchmark. Upstream audio fixtures and model weights are not redistributed in the Sinter source or portable app.

The Ruff gate covers fatal syntax and undefined-name correctness checks. It does
not certify that all historical formatting/style debt has been removed. Package
version metadata is read from `src/sinter/__init__.py` by Hatch; do not duplicate a
version literal in `pyproject.toml`.

## Configuration

Workbench results keep their own preparation payload and original input key.
Preparing again or opening another result asks before replacing a view with
unsaved human document edits, registry-managed form edits or a failed/unconfirmed save; an active save
must finish first. Untouched generated results do not require this extra decision.
The registry provides an opaque identity/change token, checked both after the
decision and when the new result arrives. Later edits or save changes leave the
displayed draft in place and retain the completed result for explicit opening.

**Drafts** lists the numbered results from this preparation view, with each
result's observed save state and its own inputs/evidence. Completed results that
could not replace a later edit remain directly visible outside the disclosure;
opening one requires an explicit action. Current, prepared, pending, saving,
rejected and unconfirmed states are not inferred from report names or IDs.
Keyed controls retain their disclosure state and identity during edit and save
notifications. Each notification refreshes only that draft's observed presentation;
unrelated reports are not reserialized to update a badge. A missing/failed snapshot
shows unavailable state, never an inferred save. Replacement guards still read the
actual registry. Reads and identical edit mutations do not notify recursively.

Preparing another draft and opening a specific draft use distinct decisions.
Cancel/Escape preserve the current document and return focus and scroll to the
initiating control. Successful adoption collapses Drafts and focuses the selected
report heading. Disposed Workbench views unsubscribe; a late completion stays in
Pending work without subscribing to a removed view. An acknowledged earlier save
is retained even when its displayed view has been replaced.

Corrections use the selected result's captured payload and correction metadata.
Save remains disabled while document text is waiting to be applied, with visible
Apply/Cancel guidance; this does not disable saving every generic pending record.
On phones the editor keeps its full value in a bounded-height textarea, followed
by the same Apply, Cancel and page-break controls in keyboard order.

The registry is session-only. Apply document edits and save to My workspace for
persistence; this picker is not a durable backup. Untracked auxiliary correction,
screening and campaign-log form fields are not newly qualified by this change.
Neither recovery nor replacement automatically retries a save or model request.
`tests/report_drafts.mjs` and `tests/report_replacement.mjs` check state policy.
`tools/report_source_preview_browser.py` covers two deliberately delayed local
completions and one delayed real local-save acknowledgement through the interface;
those timing controls are disclosed as test fixtures.

Meeting corrections also retain the original transcript source's capture time;
the derived report receives its own new `created_at`. Local meeting requests may
include `transcript_source` with exactly `id`, `sha256` and `retrieved_at` from the
originating report. The backend recomputes identity and hash from the unchanged
raw transcript, validates the timezone-aware timestamp, and preserves its spelling.
This preserves caller-supplied local history; it does not authenticate when a
source was captured. An absent pin means a fresh preparation. Explicitly null,
malformed or mismatched pins fail without silently recapturing the evidence;
other workflows reject this meeting-only field.

The full pin remains in the captured payload and evidence export. The shared
editable-input comparison excludes only this derived field, so it cannot create
a false stale-input notice. Correction failures are displayed beside the pending
replacement and reason; they do not replace the current document or replay the
request. `tests/test_meeting_source_snapshot.py` forces different capture and
preparation seconds, and the browser journey keeps complete source equality.

Local `brief` requests accept an optional `opening_paragraph`, up to 1,200 Unicode
code points. It replaces the default enquiry introduction, introduces a briefing
note, or supplies an agenda's explicitly labelled purpose. The form retains the
text across format changes and asks the operator to review its role. Blank input
keeps existing defaults. Invalid text is rejected before optional search/ranking;
the client counts code points and retains oversized pasted input without trimming.
Other workflows reject this field rather than ignore it.

Reports retain the raw value as `document_opening`; the form's `input_snapshot`
retains preparation inputs, while original document text and later human edits remain
separate. Literal prose cannot create headings, links, lists or page breaks.
New Workbench enquiries keep preparation notes and reference passages in evidence;
only the explicit opening, questions and recipient/sender details enter the letter.
Blank questions remain visibly missing rather than being inferred from notes.
Briefing notes and agenda items retain their background passages. Campaign sender
review keeps background in evidence for all three local formats. Casebook source
dossiers explicitly retain their selected attributed passages; every selected
excerpt is validated even when it is omitted from recipient prose.

Optional Workbench model drafting is a separate recipient-only enquiry handoff.
The editable template fields contain the title, complete validated opening,
explicit questions, recipient and sender details. Internal notes, reference bodies
and links are excluded from that handoff; the original Workbench inputs remain
local and unchanged. The model may revise the opening. Briefing/agenda model
handoffs are disabled until a matching workflow exists. The separate optional
excerpt-ranking control can still send the selected evidence it describes.
Directly authored Explore template context remains explicit model input. None
of this extends the native profile to long letter recipes.

Saved historical documents and human edits load without migration or regeneration.
Only an explicit new preparation uses the new enquiry policy.

| Variable | Purpose |
| --- | --- |
| `NEUROFORGE_BASE_URL` | Public API base; default `https://neuroforge.io/v1`. Remote URLs require HTTPS; loopback HTTP is allowed for local integrations. |
| `NEUROFORGE_MODEL` | Chat/ranking model; default `auto` discovers the sole supported model at the official endpoint. Explicit identifiers are preserved; custom endpoints require one. |
| `NEUROFORGE_API_KEY` | Optional NeuroForge credential, read only in Python and sent only to the official HTTPS `/v1` endpoint on its standard port. Alternatively use `NEUROFORGE_API_KEY=...` in `~/.sinter_key`. |
| `SINTER_API_KEY` | Explicit credential for the URL set alongside it in `NEUROFORGE_BASE_URL`. Takes precedence over the default provider key; ignored without a matching explicit URL. Never saved by Sinter. |
| `SINTER_DATA_DIR` | Local reports/watch database directory. Default `~/.sinter`. |
| `SINTER_CHROMIUM` | Optional existing Chromium executable for the browser smoke test. |

The server binds to loopback, validates Host/Origin, uses a per-launch write token, and rejects unbounded requests. It is **not** an internet-facing, authenticated multi-user server. No generation request is automatically replayed after an error or partial stream.

CLI and UI connections share the same destination-bound credential policy. Custom
HTTPS and loopback endpoints do not inherit `NEUROFORGE_API_KEY` or `~/.sinter_key`.
For a custom CLI provider, set `NEUROFORGE_BASE_URL` and `SINTER_API_KEY` together
in the process environment. In Settings, enter a session key for the selected
destination; an environment override to another destination cannot receive that
session key. API redirects are rejected, including redirects to another provider.

## CLI

```sh
sinter serve --no-browser --port 9000
sinter health
sinter chat -m "Explain rainbows in two sentences"
sinter review example.py --no-stream
sinter research "community garden grants"
sinter templates
sinter template enquiry-letter -v context="The venue has not confirmed access." -v questions="Is there an accessible entrance?" -v recipient="Venue coordinator"
sinter workbench project.json -o report.json
sinter watches --run-due
```

Install with `python -m pip install .` for the `sinter` command. `python -m sinter` is equivalent. Without installation, `python start.py` runs directly from source and opens the workbench.

`sinter` and `python -m sinter` with no arguments print help and exit. Use
`sinter serve` to open the workbench explicitly. The source `start.py` boundary
defaults to `app` only when no arguments are supplied; `--help`, `--version`
and explicit commands pass through unchanged. The shell, macOS `.command` and
Windows `.bat` wrappers delegate to that boundary and preserve arguments.
Desktop launchers also open the workbench directly.
Unreleased native launch, shared CLI operations and Python access are documented
in [the portable runtime guide](PORTABLE_RUNTIME.md). The existing web workbench
is explicitly available through `sinter app --mode browser` or `sinter serve`.
Research accepts repeated focus questions, for example:

```sh
sinter research "community garden water planning" -q "What water access is needed?" -o research.md
```

This compiles source excerpts into a research brief. `sinter template research`
is the separate, model-generated exploration workflow and is labelled accordingly.

CLI file exports validate `-o` before workflow, search, generation or speech work.
The destination must have an existing writable parent and be a regular file or
a new filename. Source files (including a custom template definition) cannot be
used as outputs through the same path, a hard link or a symbolic link; output
symlinks are rejected even when they point elsewhere. Review reports/checkpoints
must also stay outside the reviewed folder. Choose a distinct export path.

Text exports and review checkpoints are written to unique temporary files beside
the destination, flushed, and atomically replaced. A failed write or replacement
preserves the previous deliverable and removes only that operation's temporary
file. Template progress still saves complete/partial steps with their existing
incomplete labels. JSON report suffixes are case-insensitive.

## Custom templates

Add JSON or supported YAML to `~/.sinter/templates/`. Templates appear as `user:NAME` in the UI and CLI. JSON is recommended for complex prompts:

```json
{
  "name": "My source review",
  "description": "A generative draft requiring human review.",
  "variables": ["context"],
  "steps": [
    {"name": "Extract", "prompt": "List only what is explicitly stated. Preserve uncertainty:\n{{context}}", "max_tokens": 512},
    {"name": "Review", "prompt": "Check the preceding draft against the original context. List unsupported additions.", "max_tokens": 512, "stream": true}
  ]
}
```

The dependency-free YAML subset supports indented variables/steps and quoted one-line scalars. Block scalars, tags, anchors and inline collections are rejected. Malformed files do not prevent startup. Shared template execution preserves history and search URLs and reports incomplete streams explicitly.

Templates may set a top-level `system_prompt` and a per-step `include_history`
boolean (default `true`). For focused multi-step work, set `include_history: false`
and explicitly include original variables plus `{{previous}}` in each drafting and
checking prompt. This keeps the source context available without copying the full
conversation into every step. Source text remains untrusted data.

Output limits depend on the explicitly selected connection. Compatible custom
providers retain the 32–8,192 setting range. The legacy NeuroForge hybrid profile
allows up to 2,048 output tokens, 49,152 UTF-8 bytes of alternating user/assistant
messages and 8,192 bytes of initial system instructions; the dense profile caps
output at 512 tokens.

The qualified native profile is buffered only, with 1–128 output tokens, a
2,048-byte final question, at most three recent exchanges and 4,096 history bytes,
and a separate service-tokenized 512-token prompt budget. Caller system messages
are unsupported. Larger recipes, including the example above, refuse that
profile before generation and preserve their inputs. Use the visibly scoped
**Short source answer** or explicitly select a capable provider. See the
[native contract and fixtures](NATIVE_API_COMPATIBILITY.md) for exact identity,
admission and completion checks. No public token-preflight route is qualified.

Admission failures preserve the original inputs. A length-limited template step
emits `step_partial` before failing; dependent steps do not run. JSON errors include
`partial_result`, failed jobs retain it for Recent activity, and streamed output
can be downloaded with its incomplete label. No generation is automatically replayed.

## Module boundaries

| Module | Responsibility |
| --- | --- |
| `client.py`, `templates.py`, `recipes.py` | Public API transport and explicitly generative exploration. |
| `template_runs.py` | Shared collection of complete and recoverable partial template output. |
| `evidence.py`, `briefs.py`, `grants.py`, `workbench.py` | Source-constrained compilation, question navigation and conservative checks. |
| `research.py` | Source-backed research formatting and visible question-to-excerpt coverage. |
| `meetings.py`, `meeting_sources.py`, `speech.py`, `transcript_export.py` | Transcript integrity and retained provenance, optional recognition and interchange exports. |
| `casebooks.py`, `review.py` | Revisioned source collections, bounded admission, checkpointed reviews and coverage. |
| `outputs.py` | Shared source/destination validation and same-directory atomic text output. |
| `review_checkpoints.py` | Review-folder output exclusion and bounded, identity-preserving checkpoint discovery. |
| `store.py`, `jobs.py`, `server.py` | Persistence, bounded work, cancellation and local HTTP. |
| `web/home.js`, `web/app.js`, `web/workbench.js` | Overview, routing and guided tasks. |
| `web/report-drafts.js`, `web/report-replacement.js` | Session draft/save observations, exact-state replacement decisions and per-result preparation inputs. |
| `web/workbench-draft-switcher.js`, `web/workbench-draft-observations.js` | Stable draft controls and per-entry observed-state snapshots; no request, adoption or persistence authority. |
| `web/saved-report-list.js`, `web/saved-report-preview-view.js` | Selected-copy loading and bounded source indexing; separate read-only presentation with no request, save or editor authority. |
| `web/navigation.js` | One tool registry for navigation, page labels and the keyboard finder. |
| `web/audio.js`, `web/transcription.js` | Local playback, transcription controls and passage review. |

Native HTML/CSS/JavaScript are shipped without a frontend build step or external fonts. External text is never inserted through `innerHTML`. Keep source truth, model suggestions and human edits distinguishable. New features need regression tests, understandable failure states and an explicit privacy boundary.

## Distribution and licensing

`python tools/build_zipapp.py` builds `dist/sinter.pyz` with core code, web assets and Apache notices. A compatible Python interpreter is still needed; optional speech dependencies are not bundled. `python -m build` creates a wheel and source distribution.

Sinter remains Apache-2.0. Do not add proprietary ERAIS/Fracture internals, model weights, credentials, recordings or personal test data. The public-boundary check is a narrow guard, not a complete secrets, history or licensing audit. Optional packages and models retain their separate licences. See [NOTICE](../NOTICE).

## Saved copies: find, inspect and reopen

My workspace filters saved titles or references without reading every document.
Preview saved copy reads only the selected saved report. Applied human wording
takes precedence; incomplete warnings remain visible. Longer wording uses
2,400-code-point sections, including closing sections, with no further request.
Phones show compact section controls and textual incomplete/stale qualifications
before the wording. Copy details retains the complete title, date, full reference
and warning explanations in a keyboard-operable disclosure. Close restores the
visible originating control; opening remains an explicit guarded action.
Only one selected report is retained for preview; filter changes, refresh,
close and page disposal invalidate outstanding preview responses.

Preview does not register or edit a document. Open is a separate read and checks
the existing report replacement token before and after loading. Later editor or
save changes preserve the current draft. Cancel opening stops only that local
read. Close retains registry-managed pending work for explicit recovery.

The session registry keeps full saved-copy identities separately from report
content. Only a validated save acknowledgement or an explicitly opened saved ID
updates that association. Observer/view failures after acknowledgement cannot
relabel a known write as an uncertain request. Deleting another saved copy does
not clear the editor; deleting its currently open copy requires closing first.
An unconfirmed deletion remains held for an explicit list check, with no
automatic replay. This is a single-user local workflow, not shared versioning.

## Single-report JSON recovery

My workspace → Restore draft JSON admits an exported report without replacing an
open editor, project, connection setting or existing saved copy. Selection previews
locally; Restore as a new saved copy is the explicit write. This differs from a
project backup (inputs) and a complete saved-workspace backup. Preserve the original
file: restoration keeps all report fields, source identities, edited wording and
historical review/partial flags, but does not verify them as current facts.

Admission checks original UTF-8 bytes, a 2,000,000-byte limit, the report envelope,
duplicate keys, incomplete Unicode, excessive nesting and numbers that JavaScript
would round. The server separately validates its serialized request and storage
capacity. A lost or malformed acknowledgement remains unconfirmed even if the
write committed. Check saved copies before explicitly authorising an additional
copy; no request is automatically replayed. Pending text/forms must be applied or
cancelled before restoring that candidate. Acknowledged copies use normal draft
saving for later edits.

Run `node --test --test-concurrency=1 tests/report_backup.mjs tests/report_drafts.mjs`
and `python tools/report_recovery_browser.py` for admission and real-interface recovery
regressions. These source checks do not qualify an installed release.
