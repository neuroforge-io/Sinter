# Shared-service reliability

Sinter allows 660 seconds overall for a streamed operation, including opening the request. Keep-alives do not reset that clock. The 30-second idle socket timeout still detects a dead connection; the server normally emits waiting heartbeats every 10 seconds. Time is checked before and after each bounded read, including EOF; a blocking read can consume up to the remaining socket-idle allowance before that check.

Buffered chat uses a 120-second total client budget including local admission, above the public edge's 115-second budget. The dense desktop profile limits both JSON and streamed work to 90 seconds; legacy deployments may allow 105 seconds for buffered work. Select streaming for long queued conversations. Search retains its 30-second network timeout and model discovery has a 10-second timeout. These are maximum waits, never intentional delays.

A 429 means busy or rate-limited. No immediate or ambiguous-generation retry was added. Interrupted/expired output is not a complete result. Authentication, redirect refusal, response byte caps and request-local connection settings remain unchanged. Local workflows still work when the hosted model is offline.

Source changes require a new package/install to reach an already installed desktop app; an existing 0.4.0 executable is not updated by a repository merge.

The browser stream budget is 700 seconds, above the Python 660-second budget plus its final bounded socket read. Ordinary local JSON/job-status calls remain 35 seconds; polling waits for each completed status request rather than holding a single long HTTP request. Browser cancellation remains effective and no generation retry is added.

New connections use `auto` only at `https://neuroforge.io/v1`. A bounded model-list request must advertise exactly one supported model; failed or ambiguous discovery sends no generation request. Existing saved model identifiers and environment overrides stay explicit. The connection check verifies that selection against the returned list. JSON replies and every streamed JSON event must name the exact requested model; mismatches fail without replay.

New UI preferences and CLI chat default to 64 output tokens. Automatic and dense requests have an effective 512-token ceiling. Explicit legacy Fracture selections retain their 2,048-token limit; custom-provider budgets remain unchanged. Saved budgets are preserved and the effective bound is applied before dispatch. A short answer is a preview, not evidence that longer research or review tasks are qualified.

This Sinter process runs one official hosted generation at a time, with at most four active or waiting requests. Waiting consumes the existing deadline and remains cancellable; cancellation before dispatch sends no generation. The slot is released only when its response closes. Local-only jobs and custom providers keep their existing concurrency. Other Sinter processes or public clients can still fill the origin's shared queue and return 429; no request is automatically replayed. This is local coordination, not a global capacity guarantee.

Resumable online folder reviews require an explicit model identifier so their existing checkpoint fingerprint continues to bind the backend. Check the connection, copy the advertised model into Settings or `NEUROFORGE_MODEL`, then start the review. Offline planning stays local. Existing explicit-model checkpoints retain their identity.
