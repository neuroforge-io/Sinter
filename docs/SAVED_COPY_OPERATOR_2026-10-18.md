# Saved-copy operator qualification — 18 October 2026

Tested application source: `9e389b783b7c3d240494098893c515d86af930ec`.
Version: 0.5.4rc4 development candidate. This is source-workflow evidence, not
installed-release or whole-product acceptance.

## Real local workflow

A human-operated Browser session reused an existing isolated company campaign
workspace with 32 historical reports. No new checkout or workspace copy was made.
No model, hosted API, account credentials or outbound connection was used.

The operator found two identically titled letters by their opening and closing
wording, rather than guessing from timestamps. Preview left the open editor
intact. Pending clarification wording survived cancellation, an explicit switch
and recovery exactly. One acknowledged save created a separate copy; the original
32 stored report documents remained byte-for-byte unchanged.

The first session closed through the UI. A later read-only continuation reached
its recorded deadline without a report write. On resumption, the operator checked
the old process receipts and source identity, then reopened the acknowledged saved
ID without replaying the save.

The reopened copy retained the recipient, three clarification questions, explicit
submission hold and complete sender details. The actual downloaded evidence JSON
equalled the exact saved report. All Word wording was in the correct order and
matched after normalizing document list numbering and whitespace. Every original
parent-report field except the explicit applied edits was unchanged. No campaign
record changed.

At 390 × 640, keyboard Enter opened preview, its visible controls measured at least
44.5 pixels high, and document scroll width was 375 pixels. The temporary viewport
was reset and both owned tabs closed. The actual screenshot confirmed separate
paragraphs and deliberate line breaks; flattened accessibility summary text was
not evidence of a visual salutation defect.

The final continuation's Quit click was not acknowledged before its tab closed.
The finite guard subsequently stopped the listener, drained handlers and closed
the application. That proves controlled termination; it does not qualify that UI
Quit interaction. No uncertain write was retried.

## Resource and automated evidence

Local commands were sequential, low priority and protected by the shared execution
lock. Each operator server had a 96 MiB memory cap, no swap, 25% CPU quota and a
240-second internal deadline. The final server's maximum sampled RSS was
33,501,184 bytes. This excludes the browser and is not a whole-product performance
benchmark.

[Exact-source quality run 38882903437](https://github.com/neuroforge-io/Sinter/actions/runs/38882903437)
passed all 12 jobs, including Chromium, the Python platform matrix and verified
source/portable packaging. Chromium passed all ten deliverable journeys.
[WASM run 38882903762](https://github.com/neuroforge-io/Sinter/actions/runs/38882903762)
passed Chromium, Firefox and WebKit. Later green runs do not retroactively prove
descendant-process ownership in the previously failed Windows deadline case.

## Adversarial result and remaining work

Scoped scores: **UX 7.5/10, functionality 7.5/10, aesthetics 6.5/10**. The actual
phone view is readable, but repeated metadata and nested scrolling leave little
wording visible initially.

A separate source-confirmed defect remains: fixed-character sections are parsed
as independent Markdown documents. A fence plus 2,392 characters exactly fills
the first 2,400-character section. A Markdown-looking line in the next section
can become a heading, and the original closing fence can consume the following
prose as code. Raw character coverage alone does not establish preview fidelity.

The next fix must share block context with the safe Markdown renderer, retain
complete fitting blocks, show oversized continuations honestly, preserve every
character and qualification, and avoid rendering the entire saved document.
Regression evidence must include fenced text followed by real closing prose,
Unicode boundaries, ordinary rich formatting and inert unsafe markup.

Private workspace snapshots, exact saved IDs, correspondence, downloads and raw
operation receipts remain local. This receipt publishes aggregate observations
only. Native-provider usefulness, installed workflow/upgrade qualification and
the independent Windows ownership gate remain open. RC4 remains unpublished.
