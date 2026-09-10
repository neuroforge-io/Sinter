# Sinter 0.3 verification scope

This is a public API client and local community workbench, not the proprietary ERAIS/Fracture implementation.

## Executable checks

The regression suite covers transport and interrupted streams, source hashes and exact excerpts, unknown grant requirements, transcript correction integrity, uncertainty flags, document formats, question navigation, template history, subtitle escaping, speech settings, cancellation, persistence and local HTTP boundaries. CI runs core checks and packaging on Windows/macOS/Linux with Python 3.10/3.13.

Chromium integration exercises the real local HTTP server with offline fixtures: responsive dark/light layouts, keyboard skip navigation, all three workflows, exports, saves, watches, document format selection and a mocked transcription/review/export journey. The mocked browser journey does not measure recognition accuracy.

A separate speech-engine smoke test processes short pinned upstream audio fixtures and silence with the optional recogniser. It checks word timings, metadata, channel labels, an expected speech fragment, no-speech handling and exports. Receipts and screenshots are Actions artifacts. A run counts as verified only when its jobs actually pass against the relevant commit.

## Deliberate limits

- Exact quotes establish provenance, not truth, authority, currency, semantic entailment or completeness. Question matches are keyword navigation, not answers.
- Generative templates and their self-checks are unverified; the evidence workbench does not admit model-written factual prose.
- Speech recognition can omit or invent words. No benchmark of long, noisy meetings, overlapping voices or identity accuracy is claimed.
- Channel separation handles two isolated recording tracks. It is not automatic mixed-room speaker diarization, and names require human confirmation.
- Cancellation is cooperative; model loading and native processing may finish their current operation first. Long compressed audio may require substantial memory; split it before use.
- Core portability checks do not establish every optional dependency's compatibility on every OS/CPU. No native signed installer is supplied.
- Reports, exported files and SQLite storage are unencrypted. Raw audio is not saved by Sinter. Search watches require a running app.
- No PDF/DOCX ingestion, automatic official submissions or independent accessibility certification is included. Browser printing is available.
- The public-boundary scanner is not a forensic history audit or a comprehensive secret/licence scanner.

See [README](README.md), [workflow guide](docs/WORKFLOWS.md) and [transcription guide](docs/TRANSCRIPTION.md) for operational boundaries. Claims should follow test evidence, not precede it.
