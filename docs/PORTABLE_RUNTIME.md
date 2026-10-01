# One runtime, several ways to work

[Back to Sinter](../README.md)

This guide describes unreleased development. Published rc2 downloads keep their
original browser interface and frozen source. Source, Python package and zipapp
distribution require Python 3.10+. Frozen native packages include Python; their
receipts state whether Tcl/Tk and account verification are bundled.

## Open the application

```sh
python start.py
sinter app --directory ./workspace
sinter app --mode browser --directory ./workspace
sinter app --mode headless --directory ./workspace
```

The default native window uses Tcl/Tk and calls the application directly. It does
not start an HTTP server, launch a browser or run the watch scheduler. It supports
source text, revisioned projects, evidence/gap reports, report history, JSON and
Markdown exports, and an optional short source answer. **Assistant setup** provides
shared connection/model preferences without opening an external browser.

The full web workbench remains an explicit browser presentation for campaigns,
meeting tools, Word export, broader profile settings and account sign-in. Browser and
headless modes start the existing loopback server. They require an environment
that permits that server and, for browser mode, access to its URL. Follow managed
browser policy; changing presentation does not remove that policy.

Native startup checks for a working display before opening workspace storage.
Missing Tk or a display gives guidance and a nonzero exit, without starting a
browser/server fallback. The packaged executable's `--diagnose` command checks
assets and toolkit resources without contacting a provider. Resource availability
does not establish that a graphical display works.

Close the native window to stop its own jobs and exit. Save/export before closing;
unsaved edits are not a backup. Browser mode retains **Quit Sinter**; closing a
browser tab alone does not stop the server.

## A fictional offline workflow

Choose **Fictional example**, save the project, and inspect evidence and gaps.
Inspect both the readable report and exact JSON. Questions without wording matches
stay visible as gaps. Save the report to keep its historical source snapshot.

Edit the fictional lending period from 14 to 21 days, save, and inspect again.
The project gets a new revision; the saved earlier report retains 14 days. Export
the project as JSON, then restore it as a separate copy. JSON retains admitted
source metadata; Markdown is a readable report rather than a project backup.

The CLI uses the same operations. Save this fictional input as
`fictional-casebook.json`:

```json
{
  "title": "Fictional Lantern library",
  "questions": "How long is the lending period?\nWhat insurance was approved?",
  "documents": [{
    "title": "Fictional handbook.md",
    "content": "The Lantern lending period is 14 days. Renewals require staff approval."
  }]
}
```

```sh
sinter import fictional-casebook.json --kind casebook --directory ./workspace --format json
sinter run casebooks.list --directory ./workspace --format json
sinter operations casebooks.build
sinter run casebooks.build --input build.json --directory ./workspace --format text
sinter export casebook PROJECT_ID -o restored-copy.json --directory ./workspace --machine
sinter import restored-copy.json --kind casebook --directory ./restored --format json
sinter status --directory ./workspace --format json
```

Replace `PROJECT_ID` with the returned identifier. `build.json` contains its current
revision, for example `{"id":"PROJECT_ID","revision":1}`. Update with
`casebooks.save` using `id`, the current `revision`, and the changed `document`.
A stale revision is refused; it does not overwrite another edit. Use `reports.save`
to retain a completed report, then `reports.get` after reopening. Neither a source
report nor a status check tests a model.

## Preview before an optional answer

Select an exact excerpt in the native evidence view and use it for a short answer.
Review the wording, question, destination and exact request. Explicit approval
allows one request; changed inputs or connection invalidate it. The answer is an
unverified model draft, with its exact source packet retained. An excerpt cannot
establish complete-source coverage or facts absent from it.

For CLI/Python callers, inspect `template.preview`. This workflow's input is:

```json
{
  "template": "native-source-question",
  "variables": {
    "source_title": "Fictional handbook.md",
    "excerpt": "The Lantern lending period is 14 days.",
    "question": "How long is the lending period?"
  }
}
```

Preview is local. It requires an explicit model selection; `auto` does not silently
discover a model during an exact preview. Configure a verified model through
native **Assistant setup**, browser Settings or `NEUROFORGE_MODEL`. In the native
window, approve the displayed API address and explicitly load its model catalogue,
select an exact identifier and save the connection locally. Manual entry works
without discovery. Catalogue requests send no source text and do not generate an
answer or establish free inference, availability or quality. Unsaved connection
changes and successful saves reset source preview/consent. Launcher environment
overrides remain effective and are shown in Status and the setup notice.

Assistant setup uses the existing settings/model routes and the same preference
file. API keys are optional write-only session inputs: leaving an untouched field
blank retains a session key; **Forget session key** clears it. Keys never enter
saved preferences or exports. Environment/key-file credentials can still apply to
the default NeuroForge endpoint; an empty field does not establish anonymous
access. Endpoint/style changes clear draft keys and require confirmation before
contacting or saving a new destination. The `chatgpt` style uses an already
configured account; account sign-in remains in the full workbench, and a ChatGPT
subscription is separate from a provider API key. The native panel creates no
account connection or access grant. CLI operations continue to exclude credential
and account mutations.

To send, supply unchanged input to
`template.job` or `template.run`, with `consent: true` and the preview's
`context_hash`. This is a real provider operation, subject to authentication,
limits and costs. No example command here sends it. Consent and destination-bound
credential checks are the same as the web UI.

## Structured and programmatic use

```python
from sinter.runtime import Runtime

with Runtime("./workspace") as app:
    operations = app.catalog()
    contract = app.describe("casebooks.list")
    projects = app.call("casebooks.list")
    status = app.call("runtime.status")
```

Native UI, CLI and Python reuse the web application's dispatcher, storage, source
validation, provider calls and consent gates. The catalogue declares input and
effect for each exposed operation. Account/session and settings mutations remain
in the existing UI; no credential export operation is added.

JSON mode writes one `sinter-operation-result/v1` envelope to stdout, containing
`operation`, `ok`, and `result` or `error`. Progress goes to stderr. Domain results
retain original schemas and citation packets. File exports contain domain objects
rather than stdout envelopes, so they can be imported again. Exports are atomic
and refuse supplied inputs and reserved runtime state paths.

Shared-command exit codes are 0 for success, 1 for operation failure, 2 for invalid
input/usage, and 130 for interruption/cancellation. Older specialised commands
retain documented exit contracts. Piped JSON uses `--input -`; interactive stdin
is refused rather than waiting for an unseen prompt.

`app.call()` waits for its job by default. With `wait=False`, it returns the existing
job identifier; use `app.wait()` in that same runtime. Jobs are temporary and do
not survive process exit. Save/export completed results explicitly. Interrupted
provider work is never automatically replayed. Reopen/status do not resume
inference. Closing a borrowed `Runtime(application=...)` closes only its facade.

Native saved-report history/import supports completed report objects. Model-run
JSON exports retain their source packets but are not saved-report imports. Native
model answers show provenance in readable/JSON output, not the source-report
excerpt picker.

The readable native report styles headings, source quotes and bullets while
retaining the original Markdown and exact JSON exports. Ctrl+A selects all in
the window's text fields; macOS also binds Command+A. Tk's platform accessibility
bridge varies: visible labels and keyboard bindings do not establish accessible
roles/names in an external accessibility tree.

## Build and test boundaries

Native packaging bundles Python, local assets and matching Tcl/Tk by default.
`--without-native-window` explicitly produces a CLI/browser-only artifact.
Source/zipapp distribution does not bundle Python or the system toolkit. Resource
receipts distinguish `native_window_bundled` from actual display testing.

Run graphical checks on an authorised desktop with a working display.
`SINTER_NATIVE_GUI_TEST=1` enables the bounded fictional Tk journey in
`tests/test_native_window.py`; inference is mocked. Coordinate builds, aggregate
suites and GUI/browser runs with the host resource owner. Stop only processes
owned by the test. Development checks do not move deployed services to a laptop.

Windows/macOS execution, managed cloud UI access, real-model quality and release
publication require separate evidence. Linux source tests and resource receipts
do not qualify those boundaries.
