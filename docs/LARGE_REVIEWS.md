# Large reviews and timeout recovery

Sinter 0.5 preserves the post-0.4 timeout fixes and adds bounded collection review.
Do not paste an entire repository into a single template and assume every file was
reviewed. Source admission, model commentary and verified tests are different things.
Running `sinter` without arguments prints help. Use `sinter serve` to open the web
workbench; the separately packaged desktop app still opens the workbench directly.

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

Progress is stored in `<output>.checkpoint.json`. Keep the same `-o` path when
resuming. Review output must be outside a folder being reviewed so it cannot be
admitted as new source material on the next run. The default output is a sibling
of the source, including when reviewing `.`. A single-file review cannot overwrite
its input. If older reports or checkpoints are already inside a source folder,
move them outside before starting or resuming its review.
If the expected checkpoint is missing, Sinter searches only the output directory,
the source's parent directory and the current directory for a checkpoint with the
same source, question, language and API identity. A unique match is reused and its
path is displayed; progress is then saved alongside the current output. Searches
never recurse and are bounded to 1,000 entries and 20 MB of checkpoint reads. An
ambiguous or incomplete search asks you to select the original receipt explicitly:

```sh
sinter review ./src --consent --resume --checkpoint self-review.md.checkpoint.json -o recovered-review.md
```

`--checkpoint` selects the saved progress to read; the new receipt is written to
`recovered-review.md.checkpoint.json`. Invalid JSON, symbolic links and oversized
receipts receive an actionable error before any model request. Missing checkpoints
never silently start a fresh review.

Each request receives at most 6,000 source characters plus the question and source
metadata, but batches are cut at statement and line boundaries inside that window,
never mid-line, so no content is dropped and structure is preserved. The user
question is refined by a deterministic local inventory of every source - symbols,
imports and risk-shaped lines - into targeted per-batch questions about the real
functions, classes and risky lines in that batch. When code structure is present,
one small planning request may refine those questions further; an offline run, a
resume, or any missing/invalid planning reply reports the batch ledger untouched and
falls back to the deterministic questions. Every batch record stores which question
was actually asked.
A `running` checkpoint is atomically persisted **before** dispatch, then
updated after the response. If that first write fails, no request is sent.
Completed batches are reused only when the collection, question, endpoint, model
and language hint match. Creation time is retained; update time changes on saves.
The endpoint includes `NEUROFORGE_BASE_URL`; changing providers or the model is a
new review. Restore the original environment settings to resume the old receipt,
or use a new output path without `--resume`. `--retry-uncertain` cannot override
this identity check.
Checkpoint fingerprints include the review engine, so checkpoints written by an
earlier chunking or prompt layout are rejected as different inputs instead of misread.

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
explicit resume may retry it. A response is treated as complete when it contains a
verbatim source quote, a finding tied to existing source lines and specific source
words, a DEMONSTRATED/SUSPECTED finding carrying a concrete phrase from the source,
an unlabelled defect that retains a longer source phrase, or an explicit no-issues
result. Missing-source refusals cannot pass by repeating a source word or a clean-result
phrase. Line numbers and confidence labels by themselves
do not pass. This gate recognizes usable commentary; it does not verify a finding.
A received but unsupported reply remains a partial batch. Partials are
never silently repeated; an explicit resume may re-review one with a bounded
follow-up question, at most two hops, and each re-review records its attempt in the
ledger. Existing partial answers are first reassessed locally against their actual
excerpt, including answers written by the older quote-only gate and those already
at the follow-up limit. A newly recognized answer needs no repeat model request.
The terminal and report both explain the remaining attempts and recovery action.
If an answer remains vague after two follow-ups, review its saved commentary
manually or start a new review with a narrower question and a new output path;
repeated `--resume` cannot reset the limit or establish completion.
Interrupted follow-ups retain the count and earlier received commentary; explicitly
retrying an uncertain request cannot reset the follow-up budget.
No run automatically retries generation or continues issuing requests after
a provider failure. Failed, uncertain and partial results return exit code 2,
retain earlier work, and distinguish complete, failed, partial, uncertain and
not-attempted batches. These five counts are disjoint. `not_reviewed` is the
aggregate of the last four, not a sixth state. A run limited by `--max-parts` can
return 0 while leaving batches unattempted, provided every received answer passed
the commentary gate. Inspect the coverage ledger rather than interpreting that
exit code as exhaustive review.
For work left outside `--max-parts`, Sinter prints a ready-to-run continuation
command. Failed or partial results retain an honest exit code 2 and their output;
ordinary progress is never confused with a transport failure or silently promoted
to a verified review.

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
