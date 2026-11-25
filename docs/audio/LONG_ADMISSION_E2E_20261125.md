# End-to-end long-recording admission — 25 November 2026

The 1 h 44 min recording was admitted and transcribed through the real
application HTTP routes used by the browser form, not through the direct worker
harness:

```text
POST /api/recordings           {filename, expected_size}
POST /api/recordings/chunk     192 x 1 MB in order
POST /api/recordings/finish
POST /api/transcribe           {recording_id, backend: erais-native}
GET  /api/jobs/<id>?after=N    incremental events
```

| Measurement | Result |
|---|---:|
| Source / admitted bytes | 200,554,920 |
| SHA-256 | `cc7271...badb4e` (matches `sha256sum` of the source) |
| Upload | **4.38 s** for 192 chunks |
| Status | `done` |
| Duration | 6,267.34 s |
| Segments | 603 |
| Events | 604 |
| First segment | 180.6 s |
| Total elapsed | **409.88 s** (15.3× real time) |
| Peak worker RSS | 2,000.9 MB |
| Review count | 143/603 |
| Speaker distribution | A 80, B 29, C 58, D 2, E 31, F 10, G 5, H 14, I 29, J 14, K 8, L 5, Overlap 62, Uncertain 37, Unidentified 219 |
| Worker after completion | none |
| Temporary recording after job | deleted (`recordings/` empty) |

The transcription was launched with the installed default manifest and the
`erais-native` backend; no ERAIS service, network API or fallback engine was
configured.

Receipt: `docs/audio/receipts/local_multihour_admission_20261125.json`.

## Limits

- The chunk loop was driven by a qualification script over the same HTTP
  endpoints; a literal Firefox/Chromium click-through of a 191 MB file is still
  outstanding.
- The source is six concatenated meetings, not one continuous recording.
- Peak RSS was sampled from `/proc` every 0.5 s; true instantaneous peak may be
  slightly higher.
- Speaker labels are experimental and meeting-local across the concatenation.
