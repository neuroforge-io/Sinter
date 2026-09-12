# Sinter 0.5 - Community casebooks and recoverable work

## 0.5.2 - review quality

Reviews are now shaped by source structure. Every source is analysed locally for
symbols, imports and risk-shaped lines; batches are cut at statement boundaries and
each batch is asked targeted questions about the real functions and risky lines in
its own excerpt, with an optional bounded planning request that falls back cleanly to
the deterministic inventory. A received but unsupported answer counts as a defined
partial batch - never silently replayed, re-reviewable on resume with at most two
follow-up hops. Coverage reports `batches_partial` separately and exits 2 while any
partial, failed or uncertain batch remains. See docs/LARGE_REVIEWS.md.

## 0.5.1 - review reliability

A local-first workspace for fragmented notes, correspondence, policies and volunteer
handover material. New casebooks retain originals, optimistic revisions, backups,
per-question source passages and explicit coverage gaps. Optional model drafts have
an exact transfer preview, consent and unverified labels.

Large collection reviews now use bounded batches and atomic checkpoints. Recent
activity recovers tasks after a dropped browser connection; only status reads retry.
Transport deadlines are enforced between bounded reads. Long-running agent requests
can use asynchronous job endpoints.

Apache-2.0 core. Native packages bundle Python, not model weights. Packages remain
unsigned by a publisher and macOS is not notarised. Speech still requires the optional
source installation; RKC is separately installed. Source provenance and valid citation
IDs are not guarantees of truth. No official submission or communication is automatic.

See docs/CASEBOOKS.md and docs/LARGE_REVIEWS.md for limits, storage and recovery.
