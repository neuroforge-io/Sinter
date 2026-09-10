# Sinter

A polished toolkit for the [NeuroForge](https://neuroforge.io) Fracture developer-preview API. Chat, code review, research, and custom workflows — with a web GUI and CLI.

Fracture takes a model and creates a sparse, efficient version. **Sinter** is the small, useful piece you carry with you.

## Quick Start

```bash
pip install .
sinter serve
```

Opens `http://127.0.0.1:8420` in your browser.

## Install

**Python 3.10+ required.** No external dependencies.

```bash
# From source
git clone https://github.com/neuroforge/sinter
cd sinter
pip install .

# Or just run directly
python -m sinter serve
```

**Windows / Mac / Linux** — the same commands work everywhere.

## Usage

### Web GUI

```bash
sinter serve          # launches browser at localhost:8420
sinter serve -p 9000  # custom port
```

### CLI

```bash
# Interactive chat
sinter chat

# Single message
sinter chat -m "Explain rainbows in two sentences"

# Code review
sinter review myfile.py
sinter review app.js -l JavaScript -o review.md

# Research
sinter research "renewable energy storage"

# Run a template
sinter template code-review -v code="$(cat file.py)" -v language=Python
sinter template explain -v concept="quicksort" -v level="beginner"

# List templates
sinter templates

# Check API
sinter health
```

## Templates

Sinter ships with built-in templates for common workflows:

| Template | Description | Variables |
|----------|-------------|-----------|
| `chat` | Freeform chat | `message`, `system` |
| `code-review` | Multi-pass code review | `code`, `language` |
| `research` | Research + action items | `topic` |
| `summarize` | Summarize text | `text`, `format` |
| `explain` | Explain a concept | `concept`, `level` |
| `custom` | Your own prompt | `prompt` |

### Custom Templates

Create a `.yaml` file:

```yaml
name: My Template
description: Does something useful.
variables:
  - input
steps:
  - name: Step One
    prompt: "Process this: {{input}}"
    max_tokens: 512
  - name: Step Two
    prompt: "Based on the above:\n\n{{previous}}\n\nSummarize."
    max_tokens: 256
    stream: true
```

Place it in `~/.sinter/templates/` and it appears in the GUI automatically.

## API Key

Sinter works **fully keyless** — no API key needed for chat, models, or search.

To use a private key (optional):

```bash
export NEUROFORGE_API_KEY="your-key"
# or create ~/.sinter_key with:
# NEUROFORGE_API_KEY=your-key
```

## Architecture

```
src/sinter/
├── __init__.py      # version
├── client.py        # API client (chat, stream, search)
├── templates.py     # template engine
├── cli.py           # CLI entry point
├── server.py        # web server + API proxy
└── web/
    └── index.html   # single-page GUI
```

Zero external dependencies. Pure Python 3.10+ stdlib.

## License

Apache 2.0 — see [LICENSE](LICENSE).

## Links

- [NeuroForge](https://neuroforge.io)
- [Fracture API docs](https://neuroforge.io/api.md)
- [Request an API key](https://neuroforge.io/contact/)
