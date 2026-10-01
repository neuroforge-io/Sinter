# NeuroForge native API compatibility — contract v1

Sinter supports the exact public `erais-native-qwen3` buffered text contract at
`https://neuroforge.io/v1`. Protocol compatibility is separate from model quality:
the advertised native model is **unqualified for general chat** and does not claim
assistant quality. Its narrow preview is suitable for trying one short question
against a small, explicitly selected source excerpt.

The versioned public gateway fixture is
`tests/fixtures/public_native_model_api_contract.v1.json`, copied verbatim from the
NeuroForge site fixture generator. Its contract identifier is
`neuroforge.public-native-model-client-fixtures.v1`; SHA-256 is
`711feb4f774674d4e4c6ab7dbe77dada7668004d4be0014445256a03a0f5edc4`.
The 57 synthetic gateway cases record source-file hashes and the cutover receipt.
They establish reproducible protocol behavior, not live deployment availability,
language quality, a paid-service promise, or installed-client acceptance.
This pack comes from site commit `22aad400`; public worker deployment
`d0425e8a8a844833abf7daf8b026881cadc3b885` restored text discovery on
30 September 2026. Live Sinter generation acceptance is recorded separately.

| Capability | Exact native boundary |
| --- | --- |
| Transport | One buffered JSON completion; `stream: false`, `n: 1` |
| Model identity | Exactly `erais-native-qwen3`; no fallback or silent replacement |
| Output | 1–128 tokens; at most 8,192 UTF-8 bytes |
| Final user question | At most 2,048 UTF-8 bytes |
| Earlier history | At most three complete exchanges and 4,096 UTF-8 bytes total |
| Prompt | Separate 512-token budget, checked by the service's tokenizer |
| Request / response | At most 32,768 / 65,536 bytes |
| Service edge time budget | 50 seconds for the native buffered request |
| Sinter transport time budget | 55 seconds, allowing for response delivery overhead |
| Caller system instructions | Rejected; the deployed system prompt is service-owned |
| Sampling, tools, media, structured output | Outside the supported public native subset |
| Completion status | `stop` is complete; `length` stays explicitly incomplete |

Byte admission cannot establish tokenizer fit. Sinter does not guess token counts
or call an undocumented preflight endpoint. If the service rejects a byte-admitted
question, Sinter explains the separate prompt budget and preserves the original
inputs. Shorten the selected scope deliberately or choose a suitable provider;
Sinter never truncates source conditions or strips supplied system instructions.

The client's 55-second budget is separate from the service edge's 50-second
contract. It allows a response completed within the edge budget to arrive and be
read without an equal client deadline cutting it off. A shorter enclosing task
budget or cancellation still takes precedence. Sinter sends one request and
never automatically retries it; other providers and saved settings retain their
existing behavior. This source change is not installed-release qualification or
a live latency measurement.

Discovery qualifies the exact native metadata, including buffered-only text,
deployment-owned system/sampling, input/output limits, the opaque owner runtime
identifier, and the explicit quality limitations. The public metadata is text-only
even if the installed origin also has image and audio support. The public fixture
for the installed `native-world-model-api-007` metadata projects only text and
removes its audio, vision and tokenizer details. `/v1/audio/speech`, `/v1/tokenize`
and `/v1/chat/preflight` remain unqualified public routes returning 404; a media
message is rejected by text admission. Sinter infers no image/audio capability or
public tokenizer from installed-origin metadata.

A completion does **not** echo the runtime identifier; completion identity
checks therefore establish the requested model and token accounting, not a
per-completion owner attestation. Rediscover after an unavailable or identity error.

The established Fracture hybrid and dense public identities retain their separate
contracts. Saved selections remain explicit and are never rewritten because the
live model changes. Automatic selection requires one supported, unambiguous public
model, and workflows pin that resolved selection for their entire run. A custom
provider reusing the native model name does not inherit NeuroForge's restrictions
or credentials.

Settings preserve the stored output cap. Native execution applies the smaller of
that cap, the step cap, and 128; dense execution applies its 512-token ceiling.
For example, an existing stored cap of 512 remains 512 after saving an appearance
change, while a native request sends at most 128. The controls explain this
difference and allow a native cap down to 1. Custom compatible providers retain
their 32–8,192 setting range. The default automatic preview cap is 64.

Use **Short source answer** for the native preview. It sends the exact source
title, selected excerpt, question and visible embedded instructions in one user
message. The original excerpt, source hash and source identifier stay attached to
the result. Full research, letter and review recipes refuse the native profile
before their first generation; they retain the user's inputs and explain how to
choose a smaller scope or a capable provider. Existing custom transports remain
available as explicit choices.

Sinter validates the complete native JSON envelope before exposing text: object,
exact model, one choice at index 0, assistant role, no tool/function calls, safe
non-empty text, supported finish reason and bounded token accounting. Malformed
JSON, premature EOF, wrong identity, unsupported content and oversized responses
are rejected. A verified `length` answer remains available as an incomplete draft.
Cancellation and failures do not replay a generation or switch models.

Offline campaign planning, records, review and exports remain usable without a
model connection. Optional ChatGPT account access is separate: successful sign-in
or model discovery does not establish completed generation. A streamed answer whose
final completion is inconsistent remains visibly incomplete; it cannot qualify
the native preview or a general assistant release.

Run the portable offline checks with:

```sh
.venv/bin/python -m pytest -q tests/test_native_contract_fixtures.py tests/test_native_profile.py
node --test tests/provider_connection.mjs tests/provider_connection_page.mjs
```

The [public NeuroForge API guide](https://neuroforge.io/api.md) is the user-facing
connection reference. Installed desktop/browser qualification and live task
acceptance are recorded separately for the versioned customer preview.

## Actual selected-source task — 1 October 2026

On source `0719ddde04bacb5f046075a55d195121201a937d`, a fresh fictional
workspace loaded live discovery, deliberately saved `erais-native-qwen3`,
previewed the exact selected material and ran one consented source question with
an output cap of 64. The answer named the recorded person, preserved the
unconfirmed meeting date and cited the retained excerpt. Inspection through the
source control showed the exact original wording; the saved report kept its
source identity, hash, original inputs and human review status of `draft`.

The test tab was closed, the local process restarted and the saved draft reopened
through a fresh browser tab. The report and preferences stayed exact, including
the explicit model selection. No generation was replayed. This test sent only
fictional, non-sensitive material to NeuroForge and used no ChatGPT allowance.

The [portable task receipt](releases/SINTER_NATIVE_SELECTED_SOURCE_ACCEPTANCE_20261001.json)
records the request and actual result. The reported 154 tokens are total usage;
the saved result does not separately expose completion-token usage. The tested
claim is a requested cap of 64, not 154 completion tokens or an independently
measured completion count. This is one useful narrow task on a source runtime,
not general assistant quality, grant eligibility, Word delivery or installed
release qualification. The native profile's general-chat limitation remains.
