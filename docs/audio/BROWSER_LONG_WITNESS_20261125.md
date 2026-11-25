# Literal Firefox 191 MB upload, restart and resume witness — 25 November 2026

## Result

Firefox 158.0 (headless, Selenium 4.52) drove the real Sinter UI against the
installed `erais-native` worker through an SSH tunnel. The full 191 MB,
1 h 44 min recording was uploaded through the browser file input, saved as a
project, cancelled after twelve committed passages, the Sinter process was
restarted, and the same project was reopened and resumed in a new browser
session.

```text
stage 1 — browser upload and save
  file                        ami_six_meetings.wav
  size                        200,554,920 bytes
  SHA-256                     cc727127...badb4e (matches source)
  upload + worker start       142.58 s
  committed before cancel     12 passages
  retained after cancel       15 passages, cursor 16
  project                     b273fb4cfe734b93a3ed92d78f72682f
  status                      cancelled

stage 2 — process restart, browser restore and resume
  listed status               cancelled, 15 passages
  opened partial transcript   committed events restored
  resume requested            75.42 s (last committed passage)
  final status                done
  attempt                     2
  final passages              603
  final cursor                605
  final duration              104:27
  new worker segments         588
  restored prior segments     15
  source present              true
  runtime                     erais-native-zipformer-gigaspeech
  source mode                 bounded_wav
  model bundle                52b171e1...388a28
```

The final transcript is visible in the browser review pane, paged at 31 pages
of 20 passages, and the saved-project row reads:

```text
done · 603 passages · 104:27 · zipformer-gigaspeech-fp32 · attempt 2
```

## Evidence

```text
docs/audio/receipts/browser/long_upload_stage1_20261125.json
docs/audio/receipts/browser/long_upload_stage2_20261125.json
docs/audio/receipts/browser/long_upload_stage1.png
docs/audio/receipts/browser/long_upload_stage2_partial.png
docs/audio/receipts/browser/long_upload_stage2_done.png
```

## Defect found by the literal browser run

The saved-project panel called `timestamp(...)` without importing it from
`transcription.js`. The panel failed with `ReferenceError: timestamp is not
defined` after a restart. The import is now fixed and the browser restore path
was re-run successfully.

## Limits

- The browser ran on the laptop against a Sinter server on the desktop through
  an SSH tunnel. Upload time therefore includes tunnel bandwidth and is not a
  localhost figure.
- The stage-1 interruption was an explicit cancel, not a SIGKILL with an
  orphaned worker. The startup `running → interrupted` path remains covered by
  tests rather than this browser witness.
- The resume still repeats VAD and speaker clustering over the whole recording;
  only recognition of the first 75.42 s was skipped.
- This is a local development witness. It is not independent qualification,
  production acceptance or a cross-platform result.
