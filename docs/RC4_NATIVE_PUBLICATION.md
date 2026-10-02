# RC4 native diagnostic publication

This source repair preserves the original native handoff, cleanup, verification,
request boundaries and normal diagnostic schemas. It does not qualify an
installation or release. No development result can admit a candidate.

The native owner retains the exact original JSON bytes intended for
`client-commands.json`, `outer.json`, `browser.json` and `owner-run.json` when their
publication fails. The shared `EvidencePublisher` accepts explicitly supplied
source-fixed writer, serializer and failure-schema hooks; its legacy defaults
remain unchanged. Native serialization remains indented, ASCII-escaped JSON with
the original platform text newline (LF on the qualified Linux host route).
Receipt contents cannot select hooks or executable code.

A source-fixed failure observer preserves the actual write/close exception
context from that exact writer activation. A later close failure cannot mask an
earlier write failure. Unrelated exception contexts are excluded; no global
tracing or runtime instrumentation is installed. Legacy callers retain their
original single-writer-exception behavior by default.

Every later diagnostic publication is attempted independently once. An
unsuccessful write receives no acknowledgement. Original first exceptions,
cleanup observations and secondary publication errors remain available in a
typed `EvidenceFailure`. Nested failures retain earlier complete bytes rather
than replaying a failed operation. Failed bytes include counts, SHA-256 hashes
and base64 encodings; they are diagnostics, never successful proof records.

Only a publication failure creates `outer-unpublished.json`,
`browser-unpublished.json` or `owner-run-unpublished.json`. If fallback publication
also fails, its originally serialized bytes remain in the exception. The native
CLI emits the complete failure record to standard error and exits 1. If that
write, short write or flush fails, its complete intended bytes and secondary
error remain on the same exception, chained from `SystemExit(1)`. No program can
guarantee durable storage when every output channel fails; this repair retains
the complete in-process evidence and never reports success in that case.

The CLI envelope keeps normal valid-Unicode UTF-8 bytes unchanged. Filesystem
surrogates are JSON-escaped, preserving the original byte filename when decoded
and passed to `os.fsencode`; this does not alter native sidecar serialization.
Record or rendering refusal attempts a fixed ASCII JSON fallback and records
both failures independently if that fallback also refuses. In that case all
original sidecar bytes, counts, hashes and original failure remain in the typed
exception, and the CLI still exits 1 chained from it. Rendering failure never
replays the failed operation or acknowledges a successful publication.

Normal success, existing native JSON schemas, ordinary body-failure exit codes
and standard output remain unchanged. Original lifecycle and resource cleanup
still run independently. The evidence tests use private fictional files and
explicit inert browser APIs; they require no Playwright installation and never
launch Chromium, Docker, a user application, model or provider. Literal old
failing controls and new passing controls establish these source boundaries.
The inert Docker path fixture uses native `Path` identity on each host, while
retaining its exact raw fixture path and digest. Linux-owner dispatch controls
explicitly supply fictional Linux metadata on other test platforms; those
controls cannot qualify those platforms or supply actual installed evidence.
Actual installed, upgrade, account-free offline, notice and exact candidate
source/tool/package/binary qualification remain separate mandatory gates.
