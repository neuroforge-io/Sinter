# Saved and restartable transcription projects — 25 November 2026

## Result

A 60-second AMI excerpt was transcribed through the installed `erais-native`
worker, saved as a project, interrupted after four committed passages, and
resumed in a **new process**:

```text
stage 1 (process A)
  project             4274e833cf2f4a83ac4ba595b27957da
  status after cancel cancelled
  committed passages  4
  event cursor        5
  resume boundary     13.62 s
  source SHA-256      39075629...f35 (file bytes)

stage 2 (process B, same workspace)
  listed status       cancelled, 4 committed passages
  compatibility       compatible, source intact, runtime identity matched
  resume requested    13.62 s
  job status          done
  attempt             2
  final passages      14
  final cursor        16
  source present      true
```

The saved segments kept their original IDs (`T0001`–`T0005`) and the resumed
worker produced `T0006`–`T0017`; no duplicate or re-recognised passage was
merged. The final runtime receipt reports `source_mode=bounded_wav`,
`resumed=true`, `resume_after_s=13.62`, FP32, leader clustering and the same
model bundle digest.

## What is persisted

```text
workspace/transcriptions/<project-id>/
    meta.json        source identity, request, runtime identity, status,
                     attempt, cursor counters, duration, source SHA-256
    events.ndjson    append-only committed session/segment/unresolved events
    source.<ext>     private copy of the recording (mode 0600)
    result.json      final combined transcript, when complete
```

The project store:
- requires consent before copying a recording;
- rejects empty files, unsupported suffixes and unknown project IDs;
- caps projects at 100 and events at 20,000;
- writes meta/result atomically and appends events under a lock;
- converts `running` to `interrupted` when the application starts, so a
  process death cannot leave a permanently running project;
- never deletes the source while a project is running.

Loading a project restores its committed segments and `next_cursor` without
starting a worker. `GET /api/transcriptions/<id>/compatibility` recomputes the
source SHA-256, checks the installed backend/model and compares the saved
runtime identity. `POST /api/transcriptions/<id>/resume` refuses incompatible
or incomplete projects, marks attempt 2, continues after the last committed
passage, and merges prior and new segments.

The review panel has an explicit **Save this recording and transcript** option,
lists saved projects after reload, opens the saved audio/transcript, and offers
resume only for interrupted/cancelled/failed projects.

## Evidence

```text
stage 1 receipt  docs/audio/receipts/transcription_restart_stage1_20261125.json
stage 2 receipt  docs/audio/receipts/transcription_restart_stage2_20261125.json
```

## Verification

```text
tests/test_transcription_projects.py   6 passed
  saved project survives a server restart with cursor/segments
  interrupted project restores and resumes after 4.0 s
  tampered source is refused
  audio endpoint serves the private copy
  consent is required before copying
  unknown identifier is refused
tests/test_sinter_longform.py          34 passed
  resume skips committed regions and rejoins the transcript exactly
```

## Limits

- Resume re-runs VAD and speaker clustering over the whole recording; only
  recognition before the boundary is skipped. For a long meeting the clustering
  pass is still repeated.
- The resumed speaker labels are produced by a fresh clustering pass; they are
  not persisted as clusterer state. If a future clustering change alters labels,
  the saved and new passages may disagree and need review.
- The project source is a full private copy on disk; it is not moved out of the
  workspace.
- Saved projects are local to one Sinter workspace and one principal; no
  cross-workspace migration or encryption-at-rest claim is made.
- The process-restart witness used a cancelled project. A hard kill during an
  active worker is covered by the `running → interrupted` startup path but was
  not exercised with an orphaned worker.
