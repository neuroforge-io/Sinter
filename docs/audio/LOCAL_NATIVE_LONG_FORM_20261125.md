# Portable local long-form transcription — 25 November 2026

## Result

A ten-minute real AMI meeting recording was transcribed by the **local
`erais-native` backend** with no configured ERAIS service, no network and no
fallback engine:

```text
recording          ES2003a, first 10 minutes, 16 kHz mono WAV
upload             18.31 MB (browser route)
backend            erais-native
runtime            erais-native-zipformer-gigaspeech
model              zipformer-gigaspeech-fp32
duration           600.0 s
segments           58
first segment      3.68 s after submission
events             59 (1 session + 58 segments)
elapsed            26.89 s  (~22x real time, 6 threads)
status             done
reference words    780
edits              223
WER                28.59%
```

Cancellation on the same recording, requested after five committed segments:

```text
status             cancelled
elapsed            6.72 s
retained           5 segments
message            Cancelled; the meeting session was closed and the partial
                   transcript keeps 5 segments.
```

No worker process remained after cancellation.

Hour scale, same runtime, on a 31 GB eight-core desktop with two worker threads:

```text
recording           six AMI meetings, 6267 s, 191.26 MB, 16 kHz mono WAV
segments            603
first segment       180.9 s (all speaker windows are embedded first)
elapsed             404.8 s (15.5x real time)
peak worker RSS     1948 MB
review triage       143/603 passages pre-flagged
status              done, no worker left running
```

Full receipts: `MULTIHOUR_QUALIFICATION_20261125.md` and
`MULTIHOUR_CANCELLATION_20261125.md`. The file is a concatenation of six
meetings, not one continuous source.

Offline proof: the installed worker was run inside a network namespace with no
interfaces:

```sh
unshare -n -r ~/.local/share/sinter/erais-audio/worker.sh < request.json
# exit 0, 1 started event, 24 segment events, 1 complete event
```

## Installation

The ERAIS repository now provides:

```sh
python3 scripts/install_sinter_native.py \
  --model-dir /path/to/native-zipformer-model \
  --install-dir ~/.local/share/sinter/erais-audio \
  --source-commit <40-character-main-revision> \
  --python /path/to/erais-venv/bin/python \
  --threads 6 \
  --runtime-id erais-native-zipformer-gigaspeech \
  --speech-manifest ~/.local/share/sinter/erais-audio/speech-manifest.json
```

The installer now snapshots the pinned source under `runtime/erais` and writes a
`$BASE`-relative launcher, so the install does not need the ERAIS checkout.
`--speaker-clustering --speaker-model campplus.onnx` bundles the CAM++ encoder.
`--rollback` restores the previous source snapshot and manifest after an
upgrade. Python and its numerical dependencies still come from the named
interpreter; see `PORTABLE_RUNTIME_20261125.md`.

It verifies the model bundle against the speech manifest, writes an executable
launcher and a `manifest.json` with:

```json
{
  "schema": "erais.audio.runtime.v1",
  "protocol_version": 1,
  "meeting_stream": true,
  "max_meeting_seconds": 14400,
  "models": ["zipformer-gigaspeech-fp32"],
  "source_revision": "5169644a50dcfa093d12d42c945499d5d4c3e642"
}
```

The manifest and speech manifest are mode 0600; the launcher is 0700. The
launcher pins the intended virtual-environment interpreter rather than resolving
its symlink to the base Python. Sinter finds the install at its default path and
lists `erais-native` as available.

## Anonymous speaker clustering

The installer can bundle the pinned CAM++ speaker encoder:

```sh
python3 scripts/install_sinter_native.py ...   --speaker-clustering   --speaker-model ~/.cache/erais-public-bench/campplus.onnx
```

It copies the encoder into the runtime directory, exports
`ERAIS_SPEAKER_MODEL`, records its SHA-256 in the manifest and sets
`speaker_diarization: true`. Sinter then sends `anonymous_speakers: true` with
each meeting request.

The installed worker uses the ONNX Runtime CAM++ donor (about 30 ms per 1.5 s
window). The native graph speaker path costs roughly a second per window and
was not viable for long meetings; it remains only as a fallback.

Measured on four AMI excerpts with leader clustering and reconciliation: 74 of
101 passages received a confident anonymous label and 49 of 51 single-speaker
pairs mapped correctly (96.1%), including ES2004a at 90.9% where the HTTP path
merges two voices. See the ERAIS receipt
`reports/audio/local_anonymous_diarization_20261125/`.

## Protocol

The local worker remains one request on stdin. In meeting mode it streams JSON
lines on stdout:

```text
{"event":"started","model":"...","source_sha256":"..."}
{"event":"segment","segment":{...}}
{"event":"complete","result":{...}}
{"event":"cancelled","reason":"..."}
```

Sinter supervises the process: it commits each segment as a job event, checks
cancellation at least every 0.5 s, sends SIGTERM on cancel, waits, then kills if
needed. Utterance-only runtimes keep the original one-shot path.

## Limits

- The browser upload route is still 25 MB; this ten-minute file fits, longer
  recordings need the API/CLI path.
- The local meeting path can run the same meeting-local anonymous clustering
  when the installer bundles the CAM++ encoder (`--speaker-clustering`). It is
  experimental; passages still carry `Uncertain` and `Unidentified` states and
  must be reviewed.
- This is a development installation tied to an ERAIS source checkout and
  virtual environment. It is not yet a standalone signed bundle, and the free
  community distribution/licensing gate remains open.
- One meeting and one ten-minute excerpt; not an independent transcription
  benchmark.
- No hosted service, no GPU and no model download are involved.
