<div align="center">
  <img src="src/sinter/web/icon.svg" width="64" height="64" alt="Sinter">
  <h1>Sinter</h1>
  <p><strong>Less busywork. More community.</strong></p>
  <p>A local-first workbench for funding research, source-linked writing<br>and meeting records you can actually review.</p>

  [![Quality checks](https://github.com/neuroforge-io/Sinter/actions/workflows/ci.yml/badge.svg)](https://github.com/neuroforge-io/Sinter/actions/workflows/ci.yml)
  [![License: Apache 2.0](https://img.shields.io/badge/license-Apache_2.0-blue)](LICENSE)
  [![Python 3.10+](https://img.shields.io/badge/Python-3.10%2B-3776AB)](https://www.python.org/downloads/)

  <p><a href="#get-started">Get started</a> &nbsp; / &nbsp; <a href="docs/WORKFLOWS.md">Workflow guide</a> &nbsp; / &nbsp; <a href="docs/TRANSCRIPTION.md">Local transcription</a> &nbsp; / &nbsp; <a href="docs/DEVELOPMENT.md">For developers</a></p>
</div>

---

## Useful work, not another blank chat box

Sinter is for the people who organise the meeting, chase the grant, collect the references and write the follow-up. Choose a task, bring the context, and prepare something useful without learning prompt engineering.

| Your task | What Sinter helps you prepare |
| :--- | :--- |
| **Find funding** | Search-backed leads, exact requirement checks, unanswered eligibility questions and recurring search watches. |
| **Write with context** | An enquiry letter, briefing note or agenda item, with a question-to-source guide and complete evidence pack. |
| **Keep meeting records** | Local transcription, passage playback, speaker-label review, traceable corrections and draft minutes. |

**You keep the final say.** Sinter does not send letters, submit applications or approve minutes. Its evidence workflows use checked source excerpts, not unbounded model-generated factual prose. Free-form AI drafting is available separately, and labelled as unverified.

## Get started

**You need Python 3.10+ and a web browser.** The core needs no third-party runtime packages, Node.js, Docker, API key or model download to try the fictional examples.

### Download and open

[Download the source ZIP](https://github.com/neuroforge-io/Sinter/archive/refs/heads/main.zip), extract it, and use your launcher:

| Windows | macOS | Linux |
| :--- | :--- | :--- |
| Double-click `Start-Sinter.bat` | Open `Start-Sinter.command` | Run `sh start-sinter.sh` |

Sinter opens a local browser window, normally at `http://127.0.0.1:8420`. **Keep the launcher window open.** Choose **Try an example** to see a complete workflow without sending anything to an external service. Press **Ctrl+C** in the launcher to stop.

Python missing? Install it from [python.org](https://www.python.org/downloads/). On Windows, enable **Add Python to PATH**. On macOS, an extracted ZIP may need `sh Start-Sinter.command` from Terminal. Do not disable your operating system's security protections. These are source launchers, not signed native installers.

### Or clone the project

```sh
git clone https://github.com/neuroforge-io/Sinter.git ~/sinter
cd ~/sinter
python3 start.py
```

Already installed? Stop Sinter, run `git pull --ff-only` in its folder, then restart. Source launchers automatically prefer the project's `.venv` when one exists.

## A better path from context to output

**1. Bring the material.** Paste notes, add text files and reference excerpts, or import a meeting transcript. A URL alone is not source evidence. Recordings can be transcribed with the optional local speech package.

**2. Make the unknowns visible.** Exact excerpts keep their source IDs, hashes and character offsets. Questions link to related wording without pretending that a keyword match is an answer. Grant checks remain unknown until the source and interpretation are confirmed by a person.

**3. Review, then use.** Copy the draft, download Markdown and JSON evidence, print through the browser or explicitly save to your local workspace. Meeting corrections preserve the original wording and a reason for the change.

[Read the workflow guide](docs/WORKFLOWS.md) for grants, letters, agenda items, meeting review and recurring searches.

## Transcribe on your computer

From the extracted or cloned Sinter folder:

```sh
python3 setup_speech.py
# Windows: py setup_speech.py
```

The helper asks permission, installs the optional speech packages into `.venv`, and checks that the speech engine loads. **It does not download a model or upload a recording.** Restart Sinter, open **Meeting minutes**, and expand **Start with an audio recording**. The initial model download is a separate, explicit choice.

Choose a model and recording language, then transcribe and listen back to individual passages. Word timings, uncertainty flags and the audio hash are retained in the downloadable JSON. Export TXT, SRT or VTT for other tools. For two genuinely isolated microphone tracks, enable channel separation; track labels are not proof of a person's identity.

**Mixed-room speaker diarization and voice identification are not implemented.** Review the recording and confirm names manually. See the [transcription guide](docs/TRANSCRIPTION.md) for formats, limits, larger files, model choices and troubleshooting.

## Local-first, with clear boundaries

| Operation | Where it happens |
| :--- | :--- |
| Examples, source compilation, transcript review and exports | On your computer. |
| Optional speech recognition | On your computer; first model download needs permission and internet access. |
| Web search and search watches | Your exact query is sent to the configured public API. |
| Optional Fracture excerpt ranking | Up to six excerpts and the project question are sent to the configured API. |
| Explore Fracture chat and templates | The submitted conversation or template context is sent to the configured API. |

Saved reports and watches live in `~/.sinter/workspace.sqlite3`, or `SINTER_DATA_DIR` when configured. **Storage and exports are not encrypted.** Unsaved browser inputs disappear on reload. Watches run only while Sinter is open; there is no installed background service or email alert system.

Provenance is not truth. A source can be wrong, old or incomplete. A recogniser can omit or invent a word. Review full official guidance, amounts, dates, names, negation and decisions before relying on an output.

## Built with NeuroForge

Sinter demonstrates the public [NeuroForge](https://neuroforge.io) Fracture and search APIs. It is a client and workflow harness: **no proprietary ERAIS/Fracture implementation or model weights are included**. The core remains dependency-free; optional engines, packages and downloaded models retain their own licences.

Keyless access is the default. Advanced settings, CLI commands, custom templates and architecture are documented in [Development & configuration](docs/DEVELOPMENT.md). Public API availability and service terms are separate from this application.

## Quality you can inspect

The [quality workflow](https://github.com/neuroforge-io/Sinter/actions/workflows/ci.yml) runs the regression suite on Windows, macOS and Linux with Python 3.10/3.13, exercises the interface in Chromium, and builds installable and portable packages. It also runs the optional speech engine on bounded public audio fixtures and silence. Test reports and screenshots are attached to Actions runs.

These are executable integration checks, **not** a benchmark of long, noisy community meetings or a guarantee of accessibility, transcription accuracy or factual correctness. See [SELF_AUDIT.md](SELF_AUDIT.md) for scope and limitations, and the [developer guide](docs/DEVELOPMENT.md) to run the checks yourself.

---

**[Apache License 2.0](LICENSE)** &nbsp; / &nbsp; [Notices](NOTICE) &nbsp; / &nbsp; [Report an issue](https://github.com/neuroforge-io/Sinter/issues)
