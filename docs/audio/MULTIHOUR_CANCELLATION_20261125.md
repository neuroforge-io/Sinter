# Multi-hour cancellation witness — 25 November 2026

Same installed worker (`erais-native-zipformer-gigaspeech`, ERAIS `9d0b9bdf8`)
and the same 1 h 44 min recording as
`MULTIHOUR_QUALIFICATION_20261125.md`. The harness requested cancellation once
committed segments reached three.

| Measurement | Result |
|---|---:|
| Status | `cancelled` |
| Segments retained | 13 |
| Cancel observed at committed segment | 13 |
| First segment | 260.3 s |
| Elapsed to stable cancellation | 264.4 s |
| Peak worker RSS | 2,501.2 MB |
| Worker processes after | 0 |
| Error | none |

The first segment takes ~4.3 minutes because all speaker windows are embedded
before recognition starts. Segments then arrive in a burst, so 13 had already
committed before the harness issued the request; the worker stopped promptly,
emitted a `cancelled` event, kept the committed partial transcript, and left no
owned process.

This is the same cancellation path the browser uses (`POST /api/jobs/cancel`),
not a harness-only switch. It complements the earlier 600 s cancellation
witness, which retained five segments.

Receipt: `docs/audio/receipts/local_multihour_cancel_20261125.json`
(job `ac756de9191f445b898585b73f190cae`).

## Remaining cancellation gaps

- Cancellation during upload is covered by `/api/recordings/cancel` unit tests,
  not by an end-to-end browser witness.
- Cancellation during model preparation is a pre-worker abort; not separately
  timed.
- Time from request to actual resource release is measured here as the process
  is gone when the harness returns, but only to harness granularity (~1 s).
