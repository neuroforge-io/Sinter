# Changelog

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
