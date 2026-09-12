# Confirmed finding closure — 12 September 2026

Follow-up to [the user-testing review](QUALITY_REVIEW_2026-09-12.md). These are
Job/Verify/Integrity/Release corrections; no Novelty/Frontier score or installer
release claim is implied. Earlier review evidence remains historical.

## 1. Destination-bound credentials (P1)

- The CLI previously inherited `NEUROFORGE_API_KEY` or `~/.sinter_key` regardless
  of the selected API URL. A shared destination policy now permits inheritance
  only at the official HTTPS origin and `/v1` base.
- Explicit custom credentials use a UI session key or `SINTER_API_KEY` paired
  with `NEUROFORGE_BASE_URL`. No custom destination reads the default key store.
- Adjacent defect: an environment URL override could forward a UI session key
  saved for another destination. Connection snapshots now omit that key.
- Regression evidence: `tests/test_connection_credentials.py` exercises actual
  `list_models` request construction with a fictional key file and mocked opener
  in CLI and UI contexts, public/environment precedence, custom HTTPS/loopback,
  alternate ports/paths, explicit custom/session keys and redirect rejection.
- Validation: credential, desktop/atlas, profile and template-reliability suites
  passed together (**184 tests**); the repository fatal Ruff gate passed.

## 2. Source-launcher startup (P1)

- Corrects the earlier F1 closeout's overbroad statement about all entry points:
  installed `sinter` and `python -m sinter` still print help without arguments;
  source `start.py` now supplies `serve` only for an empty argument list.
- Explicit help, version, serve options and other commands retain CLI behavior.
  All three platform wrappers continue to pass arguments to `start.py`.
- Regression evidence: `tests/test_review_recovery.py` uses `runpy` with a mocked
  server for the source boundary, subprocesses for bare CLI help, and real native
  wrapper execution from another directory with a spaced source path and argument.
  Windows batch execution is CI-platform-specific; the local host is Linux.
- Validation: review-recovery and tooling CLI suites passed (**106 tests**,
  **5 Windows-only wrapper cases skipped**); the fatal Ruff gate passed.

## 3. Source-safe atomic CLI exports (P2)

- `outputs.py` shares narrow source-alias/target validation and a flushed,
  same-directory atomic text writer. Review-folder exclusion remains in
  `review_checkpoints.py`; review checkpoint serialization uses the shared writer.
- Workbench, research, template and transcription destinations are checked before
  workflow/search/model/speech work. Same paths, hard links, output symlinks,
  non-regular files and invalid parents are rejected, including default filenames.
- Adjacent fixes: protect a custom template's definition from its own export;
  expand home-relative workflow/audio paths consistently; recognize `.JSON`
  report outputs. Existing template partial-output recovery is retained.
- Regression evidence: `tests/test_cli_outputs.py` covers alias admission with
  expensive operations mocked, successful real offline workbench exports and all
  transcript formats using fictional ASR output, partial write/flush/replace/
  encoding/temp-creation failures, owned-temp cleanup and late target changes.
