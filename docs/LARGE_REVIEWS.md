# Large reviews and timeout recovery

Sinter 0.5 preserves the post-0.4 timeout fixes and adds bounded collection review.
Do not paste an entire repository into a single template and assume every file was
reviewed. Source admission, model commentary and verified tests are different things.

## First inspect the scope offline

From the Sinter checkout (with its virtual environment installed):

```sh
python -m sinter review ./src --offline -o self-review.md
python tools/self_audit.py
```

The first command produces a coverage plan without a model call. The second exercises
local collection admission, exact excerpt matching and all three fictional community
workflows. Its receipt is **not** proof that the code is bug-free.

## Review small batches and keep progress

After inspecting which files were admitted and checking for private data:

```sh
python -m sinter review ./src --consent --max-parts 8 -o self-review.md
python -m sinter review ./src --consent --max-parts 8 --resume -o self-review.md
```

Each request receives at most 6,000 source characters plus the question and source
metadata. The checkpoint next to the output is atomically replaced after each
completed or failed batch. Completed batches are reused only when the collection,
question, endpoint and model match. `--resume` explicitly permits another attempt at
unfinished batches; a timed-out request may still have run at the remote service.
There are no automatic generation retries. A failed run retains earlier work and
returns exit code 2. Partial coverage from `--max-parts` is stated in the ledger.

Use `--question` to focus on a particular concern. The same mechanism works on
policies and notes, not only code. Individual batches do not establish cross-file
or whole-collection reasoning. Model statements remain unverified; run real tests.

Directory intake excludes hidden/generated folders, symbolic links, known binary
extensions and obvious credential filenames. The ledger records admission and
bounded exclusions. This is not a comprehensive secret scanner. Text inputs are
limited to 300 files, 200,000 characters per file and 2 million characters total.
Explicit single-file reviews send that file when run without `--offline`.

## HTTP clients and agents

Prefer asynchronous `/api/chat/job` or `/api/template/job` for long work. They use
the same bodies as `/api/chat` and `/api/template/run`, but return `202 {"id":...}`.
Poll `GET /api/jobs/ID`, recover using `GET /api/jobs`, or explicitly stop with
`POST /api/jobs/cancel {"id":...}`. All writes still require the current local
`X-Sinter-Token`; obtain it from `/api/session`. Do not expose this server publicly.

The UI retries only failed **status reads** with bounded backoff. It never
re-submits the generation POST. Permanent authentication/expired-result failures
lead to a recoverable status message instead of an endless loop.

Operation deadlines are separate from socket-idle timeouts. Real HTTP reads use
bounded chunks so a peer drip-feeding bytes cannot keep a response alive forever.
Control requests keep their short timeout, JSON generation has a 120-second budget,
and SSE retains the prior 660-second budget. Job cancellation propagates through
transport checkpoints. A DNS/system operation or blocked read may take until its
own timeout; cancellation is not a claim of forcible thread termination.

Local checkpoints and outputs are unencrypted. Do not store them in a source
folder that will itself be reviewed, or commit private reports accidentally.
