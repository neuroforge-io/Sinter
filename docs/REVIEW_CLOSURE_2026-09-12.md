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
