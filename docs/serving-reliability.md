# Shared-service reliability

Sinter allows 660 seconds overall for a streamed operation, including opening the request. Keep-alives do not reset that clock. The 30-second idle socket timeout still detects a dead connection; the server normally emits waiting heartbeats every 10 seconds. Time is checked before and after each bounded read, including EOF; a blocking read can consume up to the remaining socket-idle allowance before that check.

Buffered chat uses a 120-second network timeout, above the public edge's 115-second budget; the public origin still limits buffered work to 105 seconds. Select streaming for long queued conversations. Search retains its 30-second network timeout and model discovery has a 10-second timeout. These are maximum waits, never intentional delays.

A 429 means busy or rate-limited. No immediate or ambiguous-generation retry was added. Interrupted/expired output is not a complete result. Authentication, redirect refusal, response byte caps and request-local connection settings remain unchanged. Local workflows still work when the hosted model is offline.

Source changes require a new package/install to reach an already installed desktop app; an existing 0.4.0 executable is not updated by a repository merge.
