# Local ERAIS multi-hour qualification — 25 November 2026

## Result

A single 1 h 44 min 27 s recording (six concatenated AMI meetings, 191.26 MB
PCM WAV) completed end-to-end through the installed portable `erais-native`
worker with no service dependency:

| Measurement | Result |
|---|---:|
| Source duration | 6,267.34 s (104.5 min) |
| Status | `done` |
| Transcript segments | 603 |
| Incremental events | 604 |
| First segment | 285.1 s after submission |
| Processing time | 521.85 s |
| Throughput | **12.0× real time** |
| Peak worker RSS | 2,489.4 MB |
| Peak Sinter RSS | 43.0 MB |
| Worker processes after | 0 |
| Backend | `erais-native` |
| Runtime identity | `erais-native-zipformer-gigaspeech` |
| Model | `zipformer-gigaspeech-fp32` |
| Speaker diarization | enabled (experimental) |

Anonymous clusters over the concatenated recording: A 80, B 29, C 58, D 2,
E 31, F 10, G 5, H 14, I 29, J 14, K 8, L 5, `Overlap` 62, `Uncertain` 37,
`Unidentified` 219. Clusters are meeting-local and must be reviewed; because
this file concatenates six meetings, a label is not a cross-meeting identity.

Receipt: `docs/audio/receipts/local_multihour_20261125.json` (job
`a3d741dcff924f77925d31c11cb83a1d`, ERAIS `9d0b9bdf8`).

## Why it is slower than the 4-minute benchmark

The 4-minute AMI benchmark reaches 36–41× real time because most of the cost is
model warm-up. The full recording pays:

- one-time CAM++ window embedding for **all** regions before the first segment
  (5266 windows × ~30 ms ≈ 2.6 min), which is why first-segment latency is 285 s;
- full-file PCM load (191 MB) plus the region/embedding store;
- per-region recognition with 2 threads.

Memory is bounded by resident models and the retained embedding set, not by
silence: the worker held 2.49 GB for a 104-minute file, consistent with the
earlier 21-minute (1.10 GB) and 85-minute (1.94 GB) receipts.

## Two defects found and fixed by this campaign

1. Adaptive pre/post-roll overlapped adjacent VAD regions by a few hundred ms
   and the monotonicity guard aborted the run at 53 min. Overlaps up to 1 s are
   now trimmed to the previous end; larger disorder still fails.
2. The final region could round past the file duration by milliseconds and
   abort at 104 min. Region and word timings are now clamped to the
   authoritative duration.

Both have regression tests in ERAIS `tests/test_sinter_longform.py`.

Cancellation on the same recording is recorded separately; see
`MULTIHOUR_CANCELLATION_20261125.md`.

## Limits

- Six meetings concatenated, not one continuous source recording.
- WAV is loaded before processing; incremental decoding is still outstanding.
- Diarization is experimental and time-only; no DER claim is made here.
- Single host (8 vCPU desktop, 2 threads); ordinary-laptop figures differ.
