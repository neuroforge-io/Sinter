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
`ce0d7f8b5b0aba4d67640486c8e9d2fd2af6cedbd83712ac0a9030cfa763b6d7`.
The 54 synthetic gateway cases record source-file hashes and the cutover receipt.
They establish reproducible protocol behavior, not live deployment availability,
language quality, a paid-service promise, or installed-client acceptance.

| Capability | Exact native boundary |
| --- | --- |
| Transport | One buffered JSON completion; `stream: false`, `n: 1` |
| Model identity | Exactly `erais-native-qwen3`; no fallback or silent replacement |
| Output | 1–128 tokens; at most 8,192 UTF-8 bytes |
| Final user question | At most 2,048 UTF-8 bytes |
| Earlier history | At most three complete exchanges and 4,096 UTF-8 bytes total |
| Prompt | Separate 512-token budget, checked by the service's tokenizer |
| Request / response | At most 32,768 / 65,536 bytes |
| Time budget | 50 seconds for the native buffered request |
| Caller system instructions | Rejected; the deployed system prompt is service-owned |
| Sampling, tools, media, structured output | Outside the supported public native subset |
| Completion status | `stop` is complete; `length` stays explicitly incomplete |

Byte admission cannot establish tokenizer fit. Sinter does not guess token counts
or call an undocumented preflight endpoint. If the service rejects a byte-admitted
question, Sinter explains the separate prompt budget and preserves the original
inputs. Shorten the selected scope deliberately or choose a suitable provider;
Sinter never truncates source conditions or strips supplied system instructions.

Discovery qualifies the exact native metadata, including buffered-only text,
deployment-owned system/sampling, input/output limits, the opaque owner runtime
identifier, and the explicit quality limitations. The public metadata is text-only
even if the installed origin also has image support. No image/audio capability is
inferred. A completion does **not** echo the runtime identifier; completion identity
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
