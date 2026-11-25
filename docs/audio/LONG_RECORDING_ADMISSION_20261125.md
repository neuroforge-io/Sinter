# Bounded long-recording admission — 25 November 2026

## What changed

The browser transcription form no longer posts the whole recording as one
base64 field. It now uses a chunked admission flow:

```text
POST /api/recordings            {filename, expected_size}
POST /api/recordings/chunk      {recording_id, offset, data}  (1 MB slices)
POST /api/recordings/finish     {recording_id}
POST /api/transcribe            {recording_id, model, backend, consent, ...}
POST /api/recordings/cancel     {recording_id}                (on failure)
```

Properties:

- each request is bounded to 1 MB of audio (plus JSON envelope);
- offsets must match exactly, and replaying the last accepted chunk is
  idempotent;
- the server keeps a running SHA-256 and the finished size;
- a declared size is enforced when provided, with a 2 GB hard cap;
- temporary files live under the workspace `recordings/` directory, are
  mode 0600, and are deleted when the transcription job ends or the app closes;
- the 25 MB single-payload limit no longer applies to the local workflow.

The existing base64 route remains for small inputs and older clients.

## Verification

```text
tests/test_recording_admission.py   4 passed
tests/test_runtime.py               route/job regressions pass
node --check src/sinter/web/audio.js
```

Tests cover out-of-order rejection, duplicate replay, declared-size mismatch,
incomplete finalization, path confinement, transcription hand-off, and cleanup
after the job.

## Limits

- The local ERAIS worker now decodes MP3, M4A, MP4, FLAC, OGG/Opus, WebM, AAC
  and WMA through host `ffmpeg`, and converts non-16 kHz or stereo WAV exports.
  Without `ffmpeg` it reports that instead of failing silently. Decoding still
  materializes a full PCM buffer, so memory is not yet duration-independent.
- Admission copies the file into the workspace; it does not yet use a desktop
  file handle to avoid duplication.
- Resume after an application restart is not implemented; an interrupted
  admission expires after six hours.
