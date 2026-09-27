# Sinter 0.5.3 — community workflows and bounded model access

This update brings the work since 0.5.2 into the desktop packages: clearer research
briefs, editable documents, local funding campaigns and a model connection that
checks which system is answering.

## Useful work, with the sources in view

- Find tools from the keyboard, follow source citations and keep unanswered
  research questions visible. Reports separate original excerpts from model prose.
- Save sender details locally, review or edit a draft, then export Markdown, HTML
  or Word. Word exports use the current draft text; evidence packs retain the
  original output, sources and subsequent edits.
- Keep funding opportunities, answers, quotes and next actions in a revisioned
  campaign. Missing costs and unconfirmed requirements remain open. Nothing is
  submitted to a funder automatically.
- Recover review checkpoints and completed template steps without silently
  replaying uncertain requests. Partial answers remain labelled incomplete.
- Validate CLI export destinations before expensive work and replace completed
  files atomically. Sources and custom template definitions cannot be overwritten
  by their own exports.

## Connecting to a model

New NeuroForge connections discover the sole supported advertised model and
reject answers whose model identity does not match. A dense response is not proof
of Fracture conversion or sparse quality. Saved explicit model choices and custom
provider settings are preserved.

The initial answer budget is 64 tokens. Automatic and dense NeuroForge requests
are capped at 512; explicit legacy Fracture requests allow up to 2,048. Short or
incomplete output does not qualify longer research and review tasks. Resumable
online reviews require an explicit model identifier.

One Sinter process sends one hosted generation at a time, with at most four active
or waiting requests. Waiting is cancellable and consumes the operation deadline.
This is a local limit, not reserved capacity across the public service. Requests
are never automatically replayed. Credentials stay bound to their approved API
destination; the default NeuroForge key is not inherited by a custom provider.

## Installing and updating

Close the old app, install the package for your system and reopen Sinter. Installed
apps do not update themselves. Keep backups of saved work. To change a retained
legacy selection, review the Model identifier in Settings; use `auto` for the
official NeuroForge preview or an explicit supported identifier for reviews.

Core installers bundle Python, not model weights. Local examples need no account
or API key. Speech recognition still requires the optional source installation;
RKC is installed separately. Saved data remains unencrypted on your computer.

Publication requires quality checks and installed-app receipts for all nine
platform/architecture targets at the same source commit. Check `build-manifest.json`
and `SHA256SUMS.txt` for the shipped version and hashes. ARMv7 is tested under
emulation and x86 through compatibility execution.

These remain Apache-2.0 community preview packages, without publisher signing or
macOS notarisation. Do not disable operating-system protections. Exact sources,
valid citations and model self-checks do not establish truth; review the work before
using it. The public API remains capacity-limited, without a 24/7 service guarantee.

See the [installation guide](https://github.com/neuroforge-io/Sinter/blob/v0.5.3/docs/INSTALLATION.md),
[workflow guide](https://github.com/neuroforge-io/Sinter/blob/v0.5.3/docs/WORKFLOWS.md)
and [changelog](https://github.com/neuroforge-io/Sinter/blob/v0.5.3/CHANGELOG.md).
