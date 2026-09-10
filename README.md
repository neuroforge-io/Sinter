# Sinter

**Less busywork. More community.** A local workbench for the public NeuroForge Fracture and search APIs, with guided funding discovery, source-linked briefs and letters, and transcript-preserving meeting records.

Apache 2.0. Python 3.10+. No third-party runtime dependencies in the core. No account, API key, Node.js or model download is required to try the fictional offline examples.

## Open it on your computer

Download and extract this repository, then open the launcher:

| System | Launcher |
| --- | --- |
| Windows | Double-click `Start-Sinter.bat` |
| macOS | Open `Start-Sinter.command` |
| Linux | Run `sh start-sinter.sh` |

Python 3.10 or newer must already be installed. Install it from [python.org](https://www.python.org/downloads/) when needed; on Windows, enable **Add Python to PATH**. These are source launchers, not signed native installers. On macOS, an extracted ZIP may not retain executable permissions: run `sh Start-Sinter.command` from Terminal. Do not disable operating-system security protections.

The launcher opens your browser at `http://127.0.0.1:8420`. Keep its terminal window open while using Sinter. A free port is selected when the default port is busy. Press Ctrl+C to stop. Select **Try an example** for your first run.

From a terminal on Linux/macOS:

```sh
cd ~
git clone https://github.com/neuroforge-io/Sinter.git sinter
cd ~/sinter
python3 start.py
```

From an existing Python environment:

```sh
python -m pip install .
sinter
# Other entry points:
python -m sinter serve
sinter serve --no-browser --port 9000
```

All source launchers prefer this folder's `.venv` when one exists. `start.py` runs directly from source without installing anything.

## Three useful workflows

**Find funding.** Describe the project, add reference text, and optionally search for opportunities. The report retains URLs, excerpts and retrieval times. Copy exact guideline wording into the requirement checker and confirm its currency and interpretation. Checks return `met`, `not_met` or `unknown`; overall eligibility always remains `review_required`. Missing information, fictional examples and unconfirmed requirements cannot establish eligibility.

**Briefs and letters.** Gather notes, text files, questions and references into a structured briefing, enquiry-letter scaffold and evidence register. Download Markdown, copy the draft text, export the complete JSON evidence pack, or print/save through your browser. This is source-constrained compilation, not unrestricted narrative synthesis or a rich-text editor.

**Meeting records.** Import TXT, Markdown, JSON segments, SRT or VTT. Confirm speaker labels manually. Candidate action/decision passages are highlighted without inferring attendance, votes, resolutions or deadlines. Reviewed corrections preserve original text and reasons. Minutes remain drafts until reviewed and approved outside Sinter.

The examples are explicitly fictional. They are not actual grant recommendations, meetings or eligibility advice.

## Grounding and review

The evidence workbench snapshots source text with identifiers, SHA-256 hashes, exact quotes and character offsets. Optional Fracture ranking can reorder existing excerpt IDs only: generated prose and invented IDs are not admitted into these reports. Invalid ranking falls back to deterministic selection.

This establishes **provenance, not truth, authority, currency or completeness**. Review full official guidance and surrounding context. No application can guarantee hallucination-free output. Free-form chat and custom templates remain available under **Explore Fracture** and are explicitly unverified.

Nothing sends official letters, applies for grants or approves minutes automatically.

## Saved work and recurring searches

Saving is explicit. Reports and watches live in `~/.sinter/workspace.sqlite3`; set `SINTER_DATA_DIR` to use another directory. Store important backups somewhere safe. SQLite and exports are not encrypted.

Search watches support hourly/daily/weekly checks, restart-safe leases, bounded retries and new/changed/not-returned result comparisons. They run only while Sinter is running. Closing the app stops checks; overdue work resumes after restart. There is no installed background service or email notification system. A missing search result is never treated as proof an opportunity has closed.

Calendar export creates review reminders and optional human-confirmed closing-date entries. Confirm the closing time and time zone separately. Importing a calendar does not run Sinter or automatically update an earlier import.

## Optional local audio transcription

Install the optional speech extra into a virtual environment:

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install '.[speech]'
python start.py
```

On Windows, activate with `.venv\Scripts\activate` instead. Recording permission and permission for the initial speech-model download are separate choices. The browser upload limit is 25 MB; the CLI accepts recordings up to 500 MB:

```sh
sinter transcribe meeting.wav --consent --allow-download -o transcript.json
```

The optional faster-whisper adapter processes audio locally on CPU. Its dependencies and model weights have separate licenses. **Automatic diarization and voice identity are not implemented.** Unidentified turns remain unidentified; do not assign an entire multi-speaker recording to one person. Check recognition against the recording, especially names, numbers and negation. Recognition accuracy has not been benchmarked by this release.

## Public API configuration

Keyless access is the default. Optional settings are read by the Python process, never stored in browser storage:

- `NEUROFORGE_API_KEY` (or `NEUROFORGE_API_KEY=...` in `~/.sinter_key`).
- `NEUROFORGE_BASE_URL` (default `https://neuroforge.io/v1`). Remote endpoints require HTTPS; loopback HTTP is allowed for local integrations.
- `NEUROFORGE_MODEL` (default `erais-fracture-gemma`).

Search sends the exact query. Optional ranking sends up to six excerpts and the project question. Explore Fracture sends chat/template inputs. Leave external options off for sensitive material. Upstream availability, model capability and service terms are independent of this client.

## Templates and command line

```sh
sinter health
sinter chat -m "Explain rainbows in two sentences"
sinter review example.py --no-stream
sinter research "community garden grants"
sinter templates
sinter template summarize -v text="Your text" -v format="paragraph"
sinter workbench project.json -o report.json
sinter watches --run-due
```

Templates in `~/.sinter/templates/` appear as `user:NAME`. Use JSON for complex templates. The dependency-free YAML subset accepts indented variables/steps and quoted one-line scalar prompts; anchors, tags, inline collections and block scalars are deliberately rejected. The shipped examples use supported syntax. Template execution retains prior step context and search references, and reports interrupted streams rather than treating them as success.

## Development and verification

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install '.[dev,browser]'
python -m pytest -q
python tools/check_public_boundary.py
python tools/build_zipapp.py
python dist/sinter.pyz --version
python -m playwright install chromium
python tools/browser_smoke.py
```

CI runs regression tests and packaging on Windows, macOS and Linux with Python 3.10/3.13, plus a separate Chromium integration job. Browser tests use a temporary local workspace and fictional fixtures, not live model services. Screenshots and source/build archives are attached to Actions runs. A green compilation check alone is not release verification.

`dist/sinter.pyz` is a portable core app with web assets and Apache notices. Run it with `python sinter.pyz`. A suitable Python interpreter is still required. Optional speech dependencies are not bundled.

## Structure and public boundary

`client.py` handles validated public API transport; `templates.py` shares generative workflow execution; `evidence.py`, `grants.py`, `meetings.py` and `workbench.py` implement source-constrained reports; `store.py` manages local persistence and watch leases; `jobs.py` handles bounded jobs and cancellation; `speech.py` is the optional adapter; `server.py` exposes loopback HTTP. Native frontend modules are under `src/sinter/web/`.

The repository contains client/harness code, not the proprietary ERAIS/Fracture implementation or model weights. The narrow automated public-boundary check is not a forensic audit of repository history or a legal license audit. See [LICENSE](LICENSE), [NOTICE](NOTICE) and [SELF_AUDIT.md](SELF_AUDIT.md).
