# Long recording job lifecycle — 25 November 2026

## Result

A real 10-minute AMI meeting recording (`ES2003a`, first ten minutes,
`Mix-Headset`, 16 kHz mono, 18.31 MB) was processed through Sinter's ordinary
browser upload route and the conversational ERAIS profile.

```text
status              done
model               zipformer-gigaspeech-fp32
runtime             erais-native-zipformer-gigaspeech
upload              18.31 MB
duration            600.0 s (source clock, including trailing silence)
segments            46
first segment       2.76 s after submission
events committed    47 (1 session + 46 segments)
elapsed             95.99 s (about 6.3x real time, CPU)
replay verified     full cursor range returned identical event count
```

Recognition accuracy on the same ten minutes against the manual AMI words:

```text
reference words  780
hypothesis       678
edits            242
WER              31.03%
```

Cancellation on the same recording, requested after six committed segments:

```text
status              cancelled
cancel at segment   6
received            60.0 s
elapsed             10.78 s
retained events     7 (1 session + 6 segments)
message             Cancelled; the meeting session was closed and the
                    partial transcript keeps 6 segments.
```

The ERAIS meeting session was cancelled rather than abandoned; the Sinter job
kept the segments it had already committed.

## Speaker clustering on the long recording

With `ERAIS_SPEAKER_CLUSTERING=1`, the same ten-minute recording finishes with
anonymous passage labels:

```text
segments                 46
anonymous cluster        36
ambiguous                 8
insufficient evidence     2
clusters shown            5 (Speaker A–E)
elapsed                  118.45 s (includes clustering)
events                   93 (46 provisional + 46 revised + session)
```

Every passage is flagged for speaker review. The table cannot be treated as
four-or-five known participants: one speaker can be split across clusters, and
the review step must merge or rename them by listening. The clustering is
experimental and off by default outside this development service.

## What changed

- `sinter.jobs` stores incremental events with monotonic sequence numbers,
  `received_s`, `processed_s` and a phase. `GET /api/jobs/{id}?after=N` returns
  only events after a cursor plus `next_cursor`. The full event list is not
  repeated on ordinary status polls.
- The ERAIS meeting adapter emits a `session` event after creating the session
  and a `segments` event after every accepted chunk, so progress is visible
  while audio is still being sent.
- Recording duration now comes from the decoded source clock, not the last
  recognised segment, so trailing silence is preserved (600.0 s here).
- Cancellation propagates from the job to the backend; the backend calls the
  meeting session's `/cancel` endpoint and re-raises. The job reports the
  partial transcript instead of silently discarding it.
- A job that finishes before a late cancellation request is published as
  `done` with an explicit note rather than losing completed work.
- The web helper reports the job's cancellation message, so a cancelled long
  recording explains that partial segments were retained.
- Finish-time speaker revisions are applied by sequence and revision number, and
  the review view can rename a whole speaker group while preserving every
  original label in the JSON transcript.

## Qualification harness

`tests/qualify_speech_long_recording.py` starts a private loopback Sinter app,
uploads through `/api/transcribe` exactly like the browser, follows job events
by cursor, verifies contiguity and replay, optionally cancels mid-stream, and
writes a JSON receipt. It is not collected by pytest.

```sh
SINTER_ERAIS_AUDIO_URL=http://127.0.0.1:18770 \
SINTER_ERAIS_AUDIO_TOKEN_FILE=/path/to/token \
python3 tests/qualify_speech_long_recording.py \
  --recording ES2003a_10min.wav \
  --model zipformer-gigaspeech-fp32 \
  --transcript-out transcript.json --out receipt.json
```

## Tests

```text
tests/test_job_events.py                 3 passed
tests/test_speech_job_lifecycle.py       2 passed
tests/test_speech.py                     15 passed (with related speech suites)
tests/test_speech_speaker_revision.py    1 passed
tests/test_runtime.py                    job, cursor and cancellation regressions pass
tests/transcription_speaker_groups.mjs   2 passed
```

## Limits

- One ten-minute excerpt from one meeting and one speaker cohort. This is a
  lifecycle qualification, not a meeting-transcription benchmark.
- The browser upload route admits 25 MB; longer recordings still need the CLI
  or a future local-file route. The portable native worker remains short-utterance
  only and is not part of this result.
- Speaker clustering is experimental: 36/46 passages labelled on this recording,
  five clusters for four participants, and one measured AMI meeting merged two
  voices under one label. Review must confirm or merge groups.
- No claim of product readiness, independent assessment or community
  distribution rights.
