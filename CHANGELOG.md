# Changelog

## Unreleased - user-testing quality and recovery

- Bind inherited NeuroForge credentials to the official destination in both CLI
  and UI requests. Custom providers use an explicit session key or `SINTER_API_KEY`
  paired with `NEUROFORGE_BASE_URL`; URL overrides cannot redirect UI session keys.
- Give Research its own source-backed brief in the CLI and workbench, with focus
  questions, exact highlights, source locations and explicit gaps.
- Add a searchable tool finder, grouped navigation, simpler research intake,
  clickable source citations, evidence counts and collapsible completed inputs.
- Make no-argument CLI entry points print help while preserving explicit serve
  and desktop launchers. Recover a matching review checkpoint across output paths,
  with an explicit selection for ambiguous cases and clear next-step commands.
- Accept source-grounded prose and line-referenced review findings while rejecting
  refusals and unsupported assertions. Preserve retry budgets, prior commentary and
  uncertain request identity. Prevent review reports from overwriting or entering
  their own source collection.
- Keep original source fields in every community recipe step; add explicit system
  and step-task contracts. Research drafting uses bounded larger budgets and scopes
  conclusions to supplied source locations and dates.
- Preserve completed template steps and partial output across JSON, streams and
  failed jobs. Dependent steps stop, errors stay visible and no request is replayed.
- Validate token limits and public API conversation byte/shape limits locally,
  including UTF-8 input. Reject missing atlas-answer consent before job admission.
- Make developer tool help work without optional packages and report missing
  setup clearly without turning an unexecuted check into a pass.

Model drafts and self-checks still require human review. Source matching is lexical,
not semantic verification. Partial review coverage still returns exit code 2.

## 0.5.2 - review quality

- Analyse each source deterministically (symbols, imports and risk-shaped lines) and
  derive per-batch review questions grounded in that inventory, so batches are asked
  about real functions and risky lines instead of generic 'review everything' work.
- Optionally refine the question plan with one small model call only when code
  structure is present; a missing or malformed plan falls back to the deterministic
  inventory questions without touching the batch ledger.
- Cut batches at statement and line boundaries (never mid-line) so content stays
  contiguous while structure is preserved; summary line numbers are recorded on each
  chunk. Checkpoint fingerprints now include the review engine so older chunk layouts
  are rejected cleanly instead of misread.
- Treat a received but unsupported reply (no verbatim quote of the material and no
  explicit result) as a defined partial batch: it is never silently repeated, and an
  explicit resume can re-review it with a bounded follow-up question, at most two
  hops, each re-review recorded in the ledger.
- Add per-batch adaptive answer budgets and a consistent review prompt that requires
  verbatim quotes, line numbers, DEMONSTRATED/SUSPECTED labels and an explicit
  nothing-demonstrated statement with a check list.
- Report `batches_partial` separately and return exit code 2 while any partial, failed
  or uncertain batch remains. Coverage counts stay disjoint.

## 0.5.1 - review reliability

- Persist in-flight review checkpoints before dispatch; require explicit permission
  to retry uncertain remote outcomes, including ambiguous legacy failure records.
- Preserve creation time and include a validated language hint in request data and
  checkpoint identity. Reject duplicate or malformed checkpoint batch records.
- Report disjoint complete/failed/uncertain/not-attempted coverage and actual
  requests per invocation. Completed batches remain reusable without replay.
- Admit bounded UTF-8 configuration and extensionless text; prioritise operational
  files, reject suspected secrets and binary data, and record original-byte hashes,
  exclusion totals and discovery/detail truncation.
- Stop treating zero-overlap excerpts as relevant evidence. A missing lexical match
  is explicitly not proof that the sources contain no answer.
- Read package version from one source and add fatal Ruff checks to the test matrix.

This release does not implement durable server job storage, background GUI review,
PDF/DOCX extraction, semantic retrieval or cross-document synthesis. Model commentary
is not independent verification. Runtime core dependencies remain empty.
