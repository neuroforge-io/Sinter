# Development and configuration

[Back to Sinter](../README.md)

## Install and test

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install '.[dev,browser]'
python -m pytest -q
python -m ruff check --select E9,F63,F7,F82 src tests tools
python tools/check_public_boundary.py
python tools/build_zipapp.py
python dist/sinter.pyz --version
python -m playwright install chromium
python tools/browser_smoke.py
```

Windows activation: `.venv\Scripts\activate`. Browser integration uses fictional local fixtures and a temporary workspace. It must run in an environment that permits a browser to access its local HTTP server; do not bypass managed browser policies. The Actions workflow provides such an environment.

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
| `NEUROFORGE_MODEL` | Chat/ranking model; default `erais-fracture-gemma`. |
| `NEUROFORGE_API_KEY` | Optional credential, read only in Python. Alternatively use `NEUROFORGE_API_KEY=...` in `~/.sinter_key`. |
| `SINTER_DATA_DIR` | Local reports/watch database directory. Default `~/.sinter`. |
| `SINTER_CHROMIUM` | Optional existing Chromium executable for the browser smoke test. |

The server binds to loopback, validates Host/Origin, uses a per-launch write token, and rejects unbounded requests. It is **not** an internet-facing, authenticated multi-user server. No generation request is automatically replayed after an error or partial stream.

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

## Module boundaries

| Module | Responsibility |
| --- | --- |
| `client.py`, `templates.py`, `recipes.py` | Public API transport and explicitly generative exploration. |
| `evidence.py`, `briefs.py`, `grants.py`, `workbench.py` | Source-constrained compilation, question navigation and conservative checks. |
| `meetings.py`, `speech.py`, `transcript_export.py` | Transcript integrity, optional recognition and interchange exports. |
| `casebooks.py`, `review.py` | Revisioned source collections, bounded admission, checkpointed reviews and coverage. |
| `store.py`, `jobs.py`, `server.py` | Persistence, bounded work, cancellation and local HTTP. |
| `web/home.js`, `web/app.js`, `web/workbench.js` | Overview, routing and guided tasks. |
| `web/audio.js`, `web/transcription.js` | Local playback, transcription controls and passage review. |

Native HTML/CSS/JavaScript are shipped without a frontend build step or external fonts. External text is never inserted through `innerHTML`. Keep source truth, model suggestions and human edits distinguishable. New features need regression tests, understandable failure states and an explicit privacy boundary.

## Distribution and licensing

`python tools/build_zipapp.py` builds `dist/sinter.pyz` with core code, web assets and Apache notices. A compatible Python interpreter is still needed; optional speech dependencies are not bundled. `python -m build` creates a wheel and source distribution.

Sinter remains Apache-2.0. Do not add proprietary ERAIS/Fracture internals, model weights, credentials, recordings or personal test data. The public-boundary check is a narrow guard, not a complete secrets, history or licensing audit. Optional packages and models retain their separate licences. See [NOTICE](../NOTICE).
