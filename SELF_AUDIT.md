# Sinter 0.2 verification and limits

This document replaces the old model-generated self-audit. Claims below describe implemented boundaries, not a guarantee of correctness.

## Corrected integration gaps

The first upgrade branch retained the old inline-script HTML entry point, obsolete MIT/version metadata, unsupported YAML examples and a compile-only workflow. The finishing revision connects the modular UI, aligns the Apache-2.0 package metadata, supplies source launchers and a portable zipapp builder, and runs actual regression/browser checks.

Blank grant/profile values now remain unknown. The maximum calendar date is rejected when an exclusive end date cannot be represented. Job retention is measured from completion, not submission.

## Reproducible checks

Run `python -m pytest -q`, `python tools/check_public_boundary.py`, `python tools/build_zipapp.py`, and `python tools/browser_smoke.py` as documented in README. See the GitHub Actions results for the exact tested commit. Tests cover fictional workflows, source offsets, invalid model IDs, retained URLs, grant uncertainty, transcript formats/corrections, template history, real-loopback HTTP guards, incomplete streams, SQLite persistence, watch leases/retries, job cancellation/retention and zipapp assets.

The browser script exercises keyboard navigation, dark/light/mobile layouts, all offline workflows, report/evidence downloads, local saves, corrected transcripts, watch controls, calendar export, safe DOM rendering and SSE framing. It blocks unexpected external browser requests. The verification matrix is Linux/macOS/Windows with Python 3.10/3.13; the browser job is Chromium on Linux.

Live public API interoperability, real-audio accuracy and novice installation usability require separate real-world testing. Browser automation and tests do not constitute an accessibility certification or a formal security audit.

## Deliberate boundaries

- Source hashes and matching quotes establish provenance, not source truth, current authority or complete semantic coverage. Optional model ranking only reorders existing excerpt IDs.
- Grant checks compare human-entered requirements. Overall eligibility is never automatically approved. Closing dates need human confirmation.
- Transcription is optional and local; automatic speaker separation and voice identity are not implemented. Human-labelled transcript turns and corrections remain reviewable.
- Draft letters/minutes are not sent or approved automatically. There is no unrestricted scraping, PDF/DOCX ingestion, rich-text editor or automated email alert service.
- Searches run only while the application is running. Restart-safe does not mean an always-on service.
- Local storage and exported files are unencrypted. Protect the computer and avoid sending sensitive notes through optional remote services.
- The HTTP server is loopback-only, not a production Internet-facing or multi-user service. Host/Origin/token checks are defense in depth, not a defense against another trusted local process.
- The core runtime has no third-party dependencies. Optional speech and development dependencies have their own licenses. The unchanged Apache LICENSE applies to Sinter, not to proprietary API implementations or independently downloaded model weights.
