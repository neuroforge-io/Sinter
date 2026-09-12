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
metadata. A `running` checkpoint is atomically persisted **before** dispatch, then
updated after the response. If that first write fails, no request is sent.
Completed batches are reused only when the collection, question, endpoint, model
and language hint match. Creation time is retained; update time changes on saves.

A timeout, cancellation or interrupted process can leave the remote result unknown.
Ordinary `--resume` preserves completed work and continues unattempted batches;
it does **not** replay an uncertain request. Check with the provider first. To
explicitly authorise potentially duplicated remote work:

```sh
python -m sinter review ./src --consent --resume --retry-uncertain --max-parts 8 -o self-review.md
```

This permission applies only to requests attempted in this invocation. Uncertain
batches outside its budget remain blocked on a later ordinary resume. Older
checkpoints with ambiguous `failed` records are treated conservatively as uncertain.
A received but empty or truncated response is a definitive failed batch; another
explicit resume may retry it. No run automatically retries generation or continues
issuing requests after a provider failure. Failed or uncertain results return exit
code 2, retain earlier work, and distinguish complete, failed, uncertain and
not-attempted batches. These four counts are disjoint. `not_reviewed` is the aggregate
of the last three, not a fifth state. Bounded partial runs can return 0; inspect the
coverage ledger rather than interpreting that exit code as exhaustive review.

Use `--question` for a particular concern and `--language` for a language hint sent
with each excerpt. The same mechanism works on policies and notes, not only code.
Individual batches do not establish cross-file or whole-collection reasoning.
Model statements remain unverified; run real tests.

## Admission is part of the result

Directory intake admits bounded UTF-8 text, including extensionless files and
unfamiliar text extensions. Known CI/tooling folders such as `.github` and selected
configuration dotfiles are eligible; generated/private folders, links, known
binary/document formats, obvious credential filenames and suspected secret content
are excluded. Eligible operational contracts are prioritised within the discovered
set so ordinary implementation files do not consume every document slot first.

The ledger includes byte sizes and SHA-256 hashes of the original file bytes, counts
and reasons for exclusions, and explicit flags when discovery or detail recording
is incomplete. A UTF-8 byte-order mark may be removed for review; the byte hash still
identifies the original file. Discovery is capped at 10,000 file/directory entries,
admission at 300 files, 200,000 characters per file and 2 million characters total.
Only 500 detailed skipped-file and excluded-directory records are retained; totals
remain available. Excluded directory contents are not individually inventoried.

Secret checks are conservative heuristics, **not a guarantee**. Inspect the offline
ledger and actual admitted content before consenting. Explicit single-file reviews
send the admitted file when run without `--offline`. PDF, DOCX and other binary
formats still require a separate supported text extraction step; no OCR or document
parser is bundled here.

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
