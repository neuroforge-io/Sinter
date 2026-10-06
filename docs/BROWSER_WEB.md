# Browser workbench

The browser edition runs Sinter's actual Python domain modules and route dispatcher
with pinned Pyodide 0.29.3 in a dedicated worker. It is a browser adapter, not a
second JavaScript implementation of casebooks, campaign validation or exports.

Build with `python browser/build.py dist/browser/sinter`. The builder obtains
version-pinned official Pyodide assets, verifies every SHA-256 and self-hosts them.
No runtime CDN, account, server-side workspace or secret is needed. The first
load downloads about 15 MB before compression; subsequent loads can use normal
browser caching. Local work requires no model. An initial connection is required
to load application assets; a fully offline-installable PWA is not yet provided.

## Storage and recovery

Only explicitly saved project/report/preferences and watch changes are committed.
SQLite runs in the worker's memory. An IndexedDB transaction stores a checksummed
snapshot plus the previous successful save. Save acknowledgement follows transaction
completion. Quota/transaction failure restores the pre-operation in-memory snapshot
and reports failure. Reads do not replace recovery snapshots. Web Locks prevent
two tabs from overwriting the same origin's workspace.

Export saved workspace produces bounded JSON (`sinter-browser-workspace/v1`). It
contains saved casebook/campaign documents in their existing desktop schemas,
reports, watch definitions and preferences, never account credentials or Python.
Whole-workspace import validates all entries through the original Python validators
in a temporary workspace before replacement. Invalid input leaves the original
unchanged. Restored watches are paused. Existing individual project imports and
exports remain available. Unsaved editor fields require their own backup controls.

Browser storage and downloads are unencrypted and may be cleared or evicted.
Private browsing and storage-denied contexts may not retain work. Keep explicit
file backups. The previous-save recovery button is destructive only after an
explicit confirmation; it does not merge workspaces.

## Networking and scope

Network access is limited to same-origin `/v1/models`, `/v1/search` and
`/v1/chat/completions`. No frontend API key is accepted or stored. Domain validation,
source consent/fingerprints and the native-model limits remain intact. Search sends
only the entered query. Model operations send the reviewed context. Requests are
never automatically replayed. Search watches retain explicit query consent and run
only while the page is open and active; browser sleep can delay checks.

The engine's synchronous Python network adapter uses worker-only XHR, keeping the
UI responsive. Local jobs execute serially. Stop current operation terminates the
worker and discards unfinished results; reload restores the last durable save.

The current public model is a capacity-limited short-text preview, not qualified
for general assistant quality. Source-only tools continue to work when that model
cannot fit an input. Search returns snippets/citations, not verified source facts;
empty results must not be read as proof that relevant information does not exist.

## Installed-only capabilities

Local Whisper speech, RKC executable/server access, ChatGPT OAuth, custom provider
credentials and arbitrary filesystem output paths require installed Sinter. The
webpage supports imported transcripts/atlases and browser downloads instead. These
routes fail explicitly rather than appearing to run. No claim of complete desktop
capability parity is made.

## Verification

`tests/test_browser_runtime.py` exercises casebooks, campaigns, source reports,
all four workbench workflows, export/import validation, rollback and paused watches.
The same contract can run under CPython and Pyodide. `browser/smoke.py` is the real
browser save/reload/download/multi-tab/mobile contract; the dedicated workflow runs
it on Chromium, Firefox and WebKit. Passing Node/WASM tests is not a browser pass.

## Application-managed search in chat

The optional chat control offers one exact public search topic for user review.
A bounded model planning request chooses SEARCH or ANSWER. Only SEARCH invokes
the public search tool, using that approved topic unchanged. The result trace
shows the actual query, sources and failures. With usable results, at most three
320-byte snippets enter a bounded second model call. At most one search and two
model calls run within a140-second operation budget. No arbitrary tools, changed
queries or project-file searches are accepted. This is Sinter-managed tool use;
the native public endpoint still does not accept function-calling fields.

No results or a failed provider never produce a purported source-grounded model
answer. A malformed planning response triggers an explicit error without search.
The model's tool-choice and answer quality remain subject to actual verification.
