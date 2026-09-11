# Sinter 0.4 verification scope

This is a public API client and local community workbench, not the proprietary ERAIS/Fracture implementation. A check counts as verified only when its actual run passes against the relevant source revision.

## Executable checks

Core regression tests cover transport, interrupted streams, source hashes and exact excerpts, unknown grant requirements, transcript correction integrity, document formats, template history, speech settings, cancellation, persistence and local HTTP boundaries. New checks cover settings validation and secret isolation, request-scoped configuration, atlas citations, transfer consent, selected-file path validation, CSV formula handling, calendar dates, native entry points and release-manifest rejection cases. CI runs on Windows/macOS/Linux with Python 3.10 and 3.13.

Four browser scripts exercise the actual local HTTP servers with offline fixtures: responsive themes, keyboard navigation, workflows, exports, saves, watches, document formats, transcription/review, local playback, settings persistence, community plans, RKC import/consent and the public download chooser. Mocked recognition and release metadata in browser tests are not speech accuracy or deployment evidence.

Separate integration jobs run a real optional speech engine on short pinned audio fixtures and compile a fictional collection with a pinned real RKC executable. They test interoperability rather than long noisy meetings or arbitrary atlas versions. Receipts and screenshots are retained as Actions artifacts.

Nine native targets build interpreter-bundled installers and execute installed applications. x86 execution uses compatibility environments; ARMv7 uses emulation. Windows/Linux checks include uninstall. The release publisher verifies all receipts, hashes and source identity before attaching assets. Windows/macOS binaries are not publisher-signed or notarised; installation policies may still block them.

## Deliberate limits

- Provenance is not truth, authority, freshness, entailment or completeness. Keyword matches are navigation aids.
- Generative templates, self-checks and Fracture-assisted atlas drafts remain unverified. Valid citation numbers do not prove factual support.
- RKC producer integrity/digest labels are not independently verified. Sinter's sidecar does not qualify a model provider inside RKC or rewrite canonical atlas evidence.
- Speech recognition can omit or invent words. Isolated-channel separation is not mixed-room diarization or voice identification.
- Speech engines, RKC executables and model assets are not bundled in core native installers. Optional speech currently uses a source installation.
- Cancellation is cooperative. RKC retains its own resource controls; no Linux cgroup policy is disabled by the adapter.
- Storage and exports are unencrypted. Watches run only while the application is open. Browser drafts are not persistent backups.
- No PDF/DOCX ingestion, automatic official submissions, universal old-OS compatibility or independent accessibility certification is claimed.
- GitHub Pages requires one-time repository administrator enablement; a checked-in site is not proof of a live deployment.
- The public-boundary scanner is narrow, not a forensic history, complete secret or dependency-licensing audit.

See the [README](README.md), [installation](docs/INSTALLATION.md), [workflow](docs/WORKFLOWS.md), [atlas](docs/ATLAS.md) and [transcription](docs/TRANSCRIPTION.md) guides.
