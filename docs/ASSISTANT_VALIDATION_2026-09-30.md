# Optional assistant validation — 30 September 2026

This checkpoint adds optional model connections and a campaign assistant. It is
not a claim that Sinter autonomously runs campaigns or that every product flow is
10/10. All model suggestions remain drafts; campaign decisions and outgoing
communications require separate action.

## What changed

- Settings connects NeuroForge, ChatGPT plan access, OpenAI API keys, Anthropic,
  Gemini and compatible local or remote servers. Model discovery checks a
  candidate connection before it is saved. Keys entered in Settings remain in
  memory; ChatGPT account credentials use protected local storage.
- Provider adapters handle their actual request and streaming protocols.
  NeuroForge's native preview stays within its small input and output limits and
  uses one request. External model credentials are not forwarded to NeuroForge
  search. Provider changes require confirmation before reusing an address.
- The campaign assistant selects a saved campaign, route, evidence checks and
  existing actions. A readable preview shows the context and destination before
  consent. The request is bound to the campaign revision and selected account;
  changed evidence or connections invalidate the earlier preview.
- Answers have a readable document and separate evidence record. The record
  retains selected source quotations, source states, actions and the exact
  request context. Suggestions do not silently change campaign records.
- Account failures leave local work available. Account switching, cancellation,
  reconnect and credential renewal are isolated from active job connections.
  Failed or uncertain generation is not automatically replayed.

## Real operator test

A personal ChatGPT account completed the actual OpenAI consent flow and model
discovery. An earlier organisation account was refused by the provider; Sinter
offered another sign-in without weakening account verification.

The operator selected the real NeuroForge campaign's nbn funding route, four
evidence checks and two existing actions. The checks deliberately retain unknown
location, connection and independently verified business-identity conditions.
Only the selected context was included. No private address, account details or
communications were added to the request.

The first generation failed with an unhelpful generic provider error. Error
decoding was corrected. A later request exposed indexed streaming text that did
not agree with the final completion snapshot. Recovery now keeps that received
text and its exact request evidence, with an explicit incomplete status.
The final operator request returned a useful 1,553-character partial answer but
an empty final response snapshot: 292 deltas, one indexed streamed segment and
no final text segments. It therefore **did not qualify as a completed answer**.
The operator saved the partial report locally; no campaign values were changed
and nothing was sent to an applicant, funder or email recipient. No retry was
automatic. This is an unresolved optional-provider completion limit, not a pass.

The provider's usage
page confirms a reset allowance and an enforced **20% Sinter app limit**, with
credit fallback disabled. A delayed usage dashboard cannot establish exact
immediate consumption, and token counts are not a plan percentage.

## Validation and performance

- The source checkpoint passed **1,414 Python tests**, with five skipped optional
  cases. Subsequent candidate-specific checks are recorded with release evidence.
- All JavaScript tests passed. Core, studio, desktop, site, casebook,
  deliverable, campaign and quality browser suites passed. Their fictional
  fixtures made no external requests. These checks establish interaction and
  recovery behaviour, not the quality of a live answer.
- The public-boundary check and offline self-audit passed. The portable zipapp
  runs without the optional account packages; unavailable account access has a
  clear setup explanation.
- Thirty local previews of the real saved campaign measured **7.32 ms median,
  8.98 ms p95 and 9.51 ms maximum**, on this host. These requests made no model
  calls. This measures local preview handling, not inference throughput.
- Actual frozen Linux x64 builds passed account-capable and explicit core-only
  runtime checks. Five version starts measured medians of 171.9 ms and 175.8 ms
  respectively. These small host samples are not cross-platform benchmarks.

## Critic findings and remaining limits

The independent implementation review found and corrected corrupt-account storage
blocking local work, incomplete credential admission, cancellation races and
generic sign-in denial wording. Packaging review found that installed-app proof
was discarded after checking it; the release gate is being strengthened to retain
and validate that proof.

An earlier UI critic assigned UX 8.5, functionality 9 and aesthetics 8 before
the real completion failures were understood. Those provisional scores are
superseded by the observed failures; they are not an acceptance score. A completed
live assistant answer is still unqualified.

Remaining limits include a guided, single-request assistant rather than an agent
that executes tools; provider-controlled ChatGPT output limits; provider eligibility
and service availability; pending execution of the new native platform matrix in
CI; and variable model adherence. Source links and snapshots establish provenance,
not eligibility or truth. NeuroForge's live generation endpoint was unavailable
in this cycle, so successful ERAIS inference is not claimed.
