# Provider readiness and free practice SOP — 2026-09-30

This pass improves connection checks and refusal before transmission. Local tests
use wholly fictional records, mocked catalogues and disposable app workspaces.
It does not qualify general model quality or paid customer delivery.

## Corrected behavior

- Official NeuroForge URL aliases (case, default HTTPS port and trailing slash)
  now share the automatic native preview size gate. Oversized selected records
  remain intact and the browser disables the request after consent.
- Custom providers require an exact model identifier. Unsupported `auto` is
  rejected during preview without discovery, credential access or generation.
- Custom providers reusing a NeuroForge model name are labelled “configured model”;
  that name alone cannot establish NeuroForge architecture or capabilities.
- The official model catalogue must advertise `application/json` before its body
  is trusted. Missing or wrong media types leave capabilities unverified.
- Generic HTTP failures retain their safe upstream status, close the response
  body and do not replay the request. Private response bodies remain undisplayed.

The credential-test catalogue fixture now advertises JSON. Its body and all
credential, destination and redirect assertions remain unchanged.

## Reproduction and validation

The new unit cases reproduced 17 failures before correction; all 22 now pass.
Four genuine Chromium journeys reproduced four visible failures before correction
and now pass: URL-alias size refusal, custom automatic-model refusal, custom model
labelling and non-JSON catalogue refusal. They record every gateway attempt and
require zero generation, unexpected gateway or external browser requests.

On this Linux checkout, the final aggregate passed **2,019 tests**, with five
existing platform skips. The focused credentials/provider set passed 387 tests.
Twelve existing native Chromium journeys also passed, including exact source
preservation, consent invalidation, bounded requests, terminal failures,
cancellation and recovery of incomplete output. The first aggregate found twelve
fake-catalogue media-type failures; correcting the fixture resolved them without
relaxing production validation or credential assertions.

Run the offline browser regression with:

```sh
python tools/provider_readiness_browser.py
# Or select an already-installed browser:
python tools/provider_readiness_browser.py --chromium /path/to/chromium
```

A unique `browser-artifacts/provider-readiness-*` directory retains the receipt
and screenshots, including failures. The existing Chromium CI job runs this tool
and uploads those artifacts. Windows/macOS execution and speech qualification
were not performed in this pass.

## Limited public smoke-test evidence

A separately approved anonymous `GET https://neuroforge.io/v1/models` returned
HTTP 200 JSON and advertised `erais-native-qwen3`. Its metadata described a
buffered text preview with maximum output 128 tokens and prompt limit 2,048 bytes;
`assistant_quality` and `account_billing_complete` were false and
`quality_scope` was `unqualified_for_general_chat`. Pricing was absent.

Exactly one approved anonymous request to
`POST https://neuroforge.io/v1/chat/completions` began at
**2026-09-30 13:40:58 UTC**, with this fictional payload:

```json
{"model":"erais-native-qwen3","messages":[{"role":"user","content":"Fictional test note: The test crate contains four wooden cubes. How many cubes are recorded in this note? Reply with the number only."}],"max_tokens":64,"stream":false,"n":1}
```

It returned HTTP 200 in **7.164 seconds**, content **`4`**, finish reason `stop`,
and usage of 54 prompt plus two completion tokens. No Authorization header,
cookies, inherited credentials, redirects or retries were used. This establishes
one correct fictional number-only response. It does not establish grounding,
general quality, free inference, billing completion or customer readiness.
Captured metadata and completion were also replayed through the Sinter client
locally; that replay made no additional remote request. Search was not tested.

## Free facilitator exercise: inspect a source before asking

Replay this exercise automatically with `python tools/native_browser.py`
(optionally add `--chromium /path/to/chromium`). That tool starts a disposable
practice workspace and supplies the local mock gateway; no participant account
or paid service is required. Use its `browser-artifacts/native-*.png` screenshots
and `native-summary.json` for facilitator review. It closes the practice app at
the end, so it is an automated demonstration rather than a persistent manual
mock service. In an ordinary manual workshop, complete the preview steps and
use those recorded mock results for discussion; hold generation until a local
fixture harness or separately reviewed model service is configured. Do not enter
personal or customer information.

1. In Explore AI, choose Templates and the short native source-question template.
2. Enter title **Fictional garden access note**, excerpt **The fictional garden
   opens Thursday. Water access needs venue approval.**, and question **What
   remains to be confirmed?**
3. Preview the exact source request. Check the displayed destination, model,
   question and full excerpt. Cancel if any differs from the intended exercise.
4. With the mock gateway in place, approve only that preview and run the template.
   Inspect the retained source beside the draft. The expected uncertainty concerns
   venue approval for water access; the fixture response is not real inference.
5. Change the excerpt and confirm that the old consent is invalidated. Try an
   oversized excerpt and confirm refusal without silently removing source text.
6. Simulate a terminal service error or incomplete response. Confirm no automatic
   retry, preserve the original input and inspect the incomplete-output label and
   recovery result before deciding what to do next.

The twelve native browser journeys exercise these interactions with fictional
sources and fixed responses. Citation identifiers and retained passages establish
what was selected; they do not prove a generated claim is supported. Human source
inspection remains necessary. Community invitations remain held pending broader
connector and grounded-quality evidence.

## Integration boundaries

ChatGPT subscription access and OpenAI API-key access are separate connection
mechanisms. This checkout implements OpenAI's documented OSS OAuth flow with
PKCE, issued client registration, identity verification and the explicit
`chatgpt.tokens.use.direct` permission for `https://api.openai.com/v1`.
[OpenAI's registration and sign-in documentation](https://developers.openai.com/siwc/token-sharing-open-source/sign-in)
was checked for that mechanism. No account was accessed and no live ChatGPT
inference ran in this pass; a subscription alone does not establish this app's
permission or an API-key entitlement.

The existing RKC adapter expects `rkc-context/v1` from loopback
`/api/v1/context`, with snapshot and citation-ID checks. Source inspection/update
compatibility still needs the corresponding RKC source contract and a shared
fictional fixture. Speculative adapter changes are held until that verification.
No authenticated remote-provider or available-local-model inference was qualified
by these mocks. Further remote requests need their destination, synthetic payload,
authentication and cost reviewed before execution.
