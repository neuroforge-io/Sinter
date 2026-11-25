# Bounded audio-source memory scaling — 25 November 2026

## What was measured

The local meeting engine was run in-process with the FP32 GigaSpeech Zipformer
loaded before timing, two threads, speech enhancement off and **anonymous
speaker clustering off**, on one 31 GB eight-core Linux desktop. `bounded` uses
`WavAudioSource` + `frame_rms_from_source` and reads each VAD region from disk;
`full` uses the previous `_read_wav_for_meeting` buffer. Peak RSS is
`getrusage(RUSAGE_SELF).ru_maxrss`.

| Input | Duration | Mode | Peak RSS | Elapsed | Throughput | Segments |
|---|---:|---|---:|---:|---:|---:|
| AMI excerpt | 600 s | bounded | 1,264.3 MB | 21.94 s | 27.4× | 82 |
| AMI excerpt | 600 s | full PCM | 1,287.1 MB | 21.15 s | 28.4× | 82 |
| Six-meeting prefix | 3,600 s | bounded | 1,350.3 MB | 125.09 s | 28.8× | 366 |
| Six-meeting prefix | 3,600 s | full PCM | 1,459.2 MB | 120.50 s | 29.9× | 366 |
| Six meetings | 6,267 s | bounded | 1,363.6 MB | 223.34 s | 28.1× | 603 |
| Six meetings | 6,267 s | full PCM | 1,554.3 MB | 223.37 s | 28.1× | 603 |
| Six meetings + 1 h | 9,867 s | bounded | **1,356.8 MB** | 344.09 s | 28.7× | 970 |

Bounded growth from 10 minutes to 104 minutes is **99.3 MB** in total
(1,264.3 → 1,363.6 MB), and almost all of that appeared between 10 and 60
minutes as transcript, region and 20 ms frame statistics accumulated. Full-PCM
growth over the same interval is **267.2 MB**, close to the added PCM buffer and
read copies. Extending bounded input to 164.5 minutes does not increase peak
RSS further (1,356.8 MB, within measurement noise of the 104-minute run), which
is the duration-independence the bounded path is meant to provide.

Recognition output is identical: both modes produce the same SHA-256, duration
and segment count for every paired input.

The throughput difference with clustering off is within 4%; bounded mode avoids
memory, not recognition work. With anonymous clustering enabled, the same
104-minute recording took 402.1 s and peaked at 1,816.9 MB in the installed
worker because the CAM++ window pass and its session dominate.

## What changed

Compressed and non-conforming WAV inputs previously fell back to the full-PCM
path. They are now decoded once to a private 16 kHz mono WAV on disk, streamed
through `WavAudioSource`, and the temporary file is removed on success or
failure. The transcript reports `source_mode = bounded_wav` for both
ready-to-stream WAV and decoded compressed input.

Receipts for each row are under
`docs/audio/receipts/memory_scaling/`. The measurement harness is
`/home/lloyd/measure_source.py` (host-local qualification tool).

## Limits

- Peak RSS includes the resident model and Python/ORT baseline, so deltas are
  more informative than absolute values.
- VAD retains one float per 20 ms frame (about 144 KB/hour); regions, speaker
  windows and transcript text still grow with content. Working memory is
  decoupled from PCM duration, not perfectly constant.
- Speaker clustering was disabled for this paired measurement; its embedding
  set is small but the CAM++ session adds a fixed ~0.4–0.5 GB.
- The 2.7-hour input is six AMI meetings plus one repeated hour; it is not one
  continuous recorded meeting.
- No lower-powered laptop or non-Linux host was measured.
