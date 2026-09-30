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
python tools/campaign_source_picker_browser.py
python tools/communication_view_browser.py
python tools/handover_appendix_browser.py
python tools/document_export_browser.py
python tools/quality_browser.py
```

The setup above includes account-verification tests on supported crypto targets.
On Intel macOS, install `.[dev,browser]` and use a supported environment for the
signed account tests.

Windows activation: `.venv\Scripts\activate`. Browser integration uses fictional local fixtures and a temporary workspace. It must run in an environment that permits a browser to access its local HTTP server; do not bypass managed browser policies. The Actions workflow provides such an environment.

Every browser integration tool accepts `--help` without Playwright installed.
The same setup runs `browser_smoke.py`, `studio_browser.py`, `desktop_browser.py`,
`casebook_browser.py`, `deliverable_browser.py`, `campaign_browser.py`,
`campaign_source_picker_browser.py`,
`communication_view_browser.py`,
`handover_appendix_browser.py`, `document_export_browser.py`,
`quality_browser.py` and `site_browser.py`. Use `--chromium /path/to/chromium` or
`SINTER_CHROMIUM` for an existing browser; the command-line option takes priority.
Missing packages or browsers fail with installation guidance and a nonzero exit
status, so an unexecuted integration test cannot silently pass CI.

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
defaults to `serve` only when no arguments are supplied; `--help`, `--version`
and explicit commands pass through unchanged. The shell, macOS `.command` and
Windows `.bat` wrappers delegate to that boundary and preserve arguments.
Desktop launchers also open the workbench directly.
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

Output limits are 32–8,192 tokens for compatible custom providers; the public
NeuroForge endpoint accepts at most 2,048. It also accepts at most 49,152 UTF-8 bytes
of alternating user/assistant messages and 8,192 bytes of initial system instructions.
Admission failures are local validation errors. A length-limited template step
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
| `meetings.py`, `speech.py`, `transcript_export.py` | Transcript integrity, optional recognition and interchange exports. |
| `casebooks.py`, `review.py` | Revisioned source collections, bounded admission, checkpointed reviews and coverage. |
| `outputs.py` | Shared source/destination validation and same-directory atomic text output. |
| `review_checkpoints.py` | Review-folder output exclusion and bounded, identity-preserving checkpoint discovery. |
| `store.py`, `jobs.py`, `server.py` | Persistence, bounded work, cancellation and local HTTP. |
| `web/home.js`, `web/app.js`, `web/workbench.js` | Overview, routing and guided tasks. |
| `web/navigation.js` | One tool registry for navigation, page labels and the keyboard finder. |
| `web/audio.js`, `web/transcription.js` | Local playback, transcription controls and passage review. |

Native HTML/CSS/JavaScript are shipped without a frontend build step or external fonts. External text is never inserted through `innerHTML`. Keep source truth, model suggestions and human edits distinguishable. New features need regression tests, understandable failure states and an explicit privacy boundary.

## Distribution and licensing

`python tools/build_zipapp.py` builds `dist/sinter.pyz` with core code, web assets and Apache notices. A compatible Python interpreter is still needed; optional speech dependencies are not bundled. `python -m build` creates a wheel and source distribution.

Sinter remains Apache-2.0. Do not add proprietary ERAIS/Fracture internals, model weights, credentials, recordings or personal test data. The public-boundary check is a narrow guard, not a complete secrets, history or licensing audit. Optional packages and models retain their separate licences. See [NOTICE](../NOTICE).
