# Synthetic connector readiness — 30 September 2026

This source change is based on `62eb966`. It fixes an evidenced model-discovery
defect and adds a free [fictional practice session](../examples/synthetic-training/README.md).
It is local development, not a published installer or a live-service qualification.
The completed Linux rc2 release and its verified public download remain separate.

## Anthropic discovery defect and repair

Sinter previously requested only the first `/models` page. A synthetic account
with a valid selected model on page two therefore failed its connection check as
“unavailable”. Two regression tests failed before the repair. Anthropic documents
pagination through `has_more`, `last_id` and `after_id`, with a default page size
of 20. [Official model-list reference](https://platform.claude.com/docs/en/api/models/list).

Discovery now follows validated, encoded cursors on the selected Anthropic
endpoint, keeps provider ordering and authentication unchanged, and applies the
existing 256-model safety bound to the accumulated catalogue. Invalid cursors,
repeated IDs, loops, empty continuation pages and oversized catalogues fail
explicitly. Partial catalogues are not presented as complete model availability.

All pages share one ten-second control-operation budget. A discovery-owned
timeout becomes a useful API error; an enclosing deadline or cancellation still
takes precedence. Regression tests cover the connection result and loopback JSON
responses for `/api/models` and `/api/health`. Other providers retain their
single-request discovery behavior.

## What is established locally

The provider transport, account, credential-isolation, error, native contract and
connection tests use fictional catalogues, harmless prompts, test credentials
and disposable local servers. They cover protocol behavior, not live account
access or a model's ability to answer accurately.

The four new CLI practice exercises ran with outbound sockets blocked and an
empty temporary data directory. Every source-backed excerpt matched its source;
sample funding stayed unknown despite an entered confirmation flag; the enquiry
retained unanswered questions; minutes retained original and corrected text.
Six additional tests verify these cases and mocked excerpt ranking. An invented
evidence ID is discarded, retaining deterministic local selection.

Validation on Linux, Python 3.12.3:

- Aggregate: **1,988 passed, five existing skips** (74.36 seconds), with an empty
  temporary HOME/data directory and outbound sockets blocked; loopback permitted.
- Focused provider/account/native-contract suite: **316 passed**, including
  **43 new** pagination and HTTP timeout regressions. Both Node provider suites
  passed. Independent review also passed the new timeout responses.
- Training: **six passed**; all four actual CLI walkthroughs completed, preserving
  exact source text and draft status without network connections.
- CI correctness lint, new-test full lint, whitespace and public boundary checks
  passed. Full-client style lint retains 57 pre-existing line-length findings;
  none were introduced by the repair.
- Offline self-audit, source CLI, dependency-free zipapp execution and isolated
  wheel/source builds passed. The source archive includes the training materials
  and regressions; the wheel contains the tested client. Build isolation used
  Hatchling 1.32.4 from public PyPI after sandbox DNS blocked the first attempt.

The pre-fix two-page catalogue and connection regressions failed as expected.
The two local HTTP checks initially encountered sandbox socket restrictions;
they passed with permitted loopback access. Remote inference, actual local-model
inference, Windows/macOS runs, speech/RKC integration and full browser journeys
were not run for this connector pass.

Training review also identified existing presentation limits: Markdown exports
are selected reports, not full source backups, and an unapproved-booking statement
is retained under “Other discussion” rather than every automatic chair-review
candidate. The practice guide explains retaining JSON originals and reading all
turns/corrections. Neither grouping nor an empty review category establishes
complete interpretation of a meeting.

No real messages, mailbox, calendar, customer material, private workspace or
derived personal summaries were used in a model payload. No credential value
was inspected, no access grant was created, and no remote model, search,
authentication or API health request was made during this work.

## Connection status and commercial limits

| Route | Implemented mechanism | Remaining qualification |
| --- | --- | --- |
| NeuroForge preview | Keyless OpenAI-compatible text API; native contract mocks | Live discovery, completion, answer accuracy, availability and cost |
| ChatGPT plan | Official OAuth sign-in, account-specific models, streaming Responses | Account eligibility, existing permission, live completion and plan cost/allowance |
| OpenAI API | Project-key OpenAI-compatible text requests | Authorised project/model, cost and live completion |
| Anthropic | Native Messages transport and paginated model discovery | Authorised account/model, cost and live completion |
| Gemini | OpenAI-compatible Gemini endpoint | Authorised account/model, cost and live completion |
| Local compatible model | Loopback OpenAI-compatible transport | Installed model and functioning local server |

Narrow local checks found no `ollama`, `llama-server`, `llama-cli`, `lmstudio` or
`lms` executable on PATH, and no listener on ports 11434, 1234, 8080 or 8000.
Other paths and ports were not searched. No model download or installation was
attempted. Local inference quality remains untested.

ChatGPT plan access uses documented OpenAI registration, PKCE and loopback
callback, then an OAuth bearer token to the public Responses endpoint with
`store: false` and `stream: true`. A subscription is distinct from ordinary
OpenAI project-key API billing. A valid identity alone does not grant plan usage;
the account must have the required permission and an available model. These
docs cover open-source/local apps; paid or remotely hosted app offerings require
the separate OpenAI interest process. This source review does not establish
approval for such an offering. [Sign-in](https://developers.openai.com/siwc/token-sharing-open-source/sign-in),
[inference](https://developers.openai.com/siwc/token-sharing-open-source/models-and-inference),
[scope](https://developers.openai.com/siwc/token-sharing-open-source).

Native ERAIS is explicitly unqualified for general chat. Its public contract
supports short buffered text only; a protocol pass cannot establish useful
grounded assistance. Community invitations remain held pending appropriate
live connector and grounding checks. Free source-only training can be reviewed
without enabling a model.

## Reviewable NeuroForge remote test — not executed

The published [API guide](https://neuroforge.io/api.md) was read on 30 September
2026. It documents the exact destinations below and keyless access without an
Authorization header. Private keys are optional; this proposal uses none.
Keyless access does not establish a zero-cost commitment. **API cost remains
unverified**, so this proposal requires review and cost resolution before any
request. No retries or fallback model substitutions are proposed.

1. `GET https://neuroforge.io/v1/models`, with no body, cookies or Authorization.
   Continue only if the exact native model and supported metadata are advertised.
2. One `POST https://neuroforge.io/v1/chat/completions`, with JSON below and no
   cookies or Authorization. Check identity, usage and completion status; assess
   the answer separately against the invented note.
3. One `POST https://neuroforge.io/v1/search`, with exactly
   `{"query":"fictional cobalt orchard wooden cubes"}`, no cookies or
   Authorization. Treat returned snippets as untrusted, not verified evidence.

```json
{
  "model": "erais-native-qwen3",
  "messages": [{
    "role": "user",
    "content": "Fictional test note: The test crate contains four wooden cubes. How many cubes are recorded in this note? Reply with the number only."
  }],
  "max_tokens": 64,
  "stream": false,
  "n": 1
}
```

For a reviewed Sinter run, explicitly bind `anonymous: true`,
`inherit_key: false` and `api_key: ""`; do not inherit environment or key-file
credentials. Discovery and search are also remote requests and need that review.
The native subset permits 1–128 output tokens, a 2,048-byte final question,
32,768-byte JSON request and a separate 512-token service prompt budget. The
client budget is 55 seconds; the service edge budget is 50. No system prompt,
sampling overrides, tools or media are proposed.

Other providers require a separate exact destination/authentication/cost/payload
review, with an authorised model selected before finalising the inference body.
No live account or model selection was performed here. Source presets alone are
not evidence of working remote integrations.

## Publication handoff

The portability change remains intact in its separate local commit
`cff8c60d60a830a2f187b9be43a32385995809f4`. Neither branch has been pushed.
No main-only development mandate was found; CI supports pull requests. Full
release assembly is main-only and requires its documented platform receipts.
Publication requires further approval; current local test results do not qualify
Windows or macOS, or change the completed rc2 release.

Before community outreach: review the exact synthetic live-test proposal and
cost, qualify the chosen provider's completion and grounded-answer behavior,
then obtain approval for the relevant code publication path. Preserve the
distinction between free OSS installation/support and a paid hosted application.
