# Sinter local audio release status — 25 November 2026

Statuses are deliberately separate. A green development receipt is not an
independent qualification, an installed runtime is not a public release, and a
public release still needs distribution rights.

| S-AUDIO gate | Development evidence | Installed on this host | Independently qualified | Publicly available |
|---|---|---|---|---|
| 01 faster-whisper preserved | code path untouched; backend selection tests pass | not re-run this sprint | no | unchanged |
| 02 browser backend selection | 4 JS tests pass | UI present | no | not released |
| 03 local ERAIS installation | installer tests pass; desktop install | yes (Linux) | no | no |
| 04 model/executable integrity | manifest + model/tree/speaker SHA-256; `--verify` passes on the installed desktop runtime; 11 installer tests | yes | no signature | no |
| 05 supported recording formats | MP3/M4A/MP4/FLAC/OGG/WebM/AAC/WMA and non-16k WAV decode tests; 30 s stereo MP3 run | yes | no | no |
| 06 long admission | 4 chunk tests + **191 MB end-to-end HTTP admission (4.38 s, SHA match, cleaned up)**; literal browser click-through still absent | yes | no | no |
| 07 stable source-time mapping | absolute-clock tests; 603 segments on 104 min via the application route | yes | no | no |
| 08 incremental transcript | 604 events on 104 min through `/api/jobs/<id>?after=`; cursor tests | yes | no | no |
| 09 cancellation/cleanup | 13 retained segments, 0 processes on 104 min; 5 retained on 10 min | yes | no | no |
| 10 saved-project restoration | saved source + cursor + events; real process-restart resume after 4 passages; 7 tests | yes (Linux) | no | no |
| 11 traceable correction | JSON revisions, corrections with original/reason; tests | yes | no | no |
| 12 anonymous speaker review | 74/101 confident labels, 49/51 pairs (96.1%) on four AMI excerpts; reversible UI | experimental | no (four-meeting cohort) | no |
| 13 consistent exports | minutes/claims share one record; SRT/VTT/TXT projections tested | yes | no | no |
| 14 evidence-grounded minutes | structured claims + stale-on-revision; 6 tests | yes | no | no |
| 15 offline operation | earlier `unshare -n` 10-min run; re-run blocked by host namespace policy | previously | no | no |
| 16 clean install/upgrade | source bundle, relocation proof, `--rollback`, `--verify`, tamper tests | yes | no | no |
| 17 free distribution rights | not obtained | no | no | **blocked** |
| 18 privacy/security qualification | no embedding export; admission confinement tests | partial | no | no |
| 19 native accessibility synthesis | injected-renderer contract only | no | no | no |

## Measured operating points

| Recording | Backend | Time | Throughput | Peak worker RSS | Result |
|---|---|---:|---:|---:|---|
| 10 min AMI | local native | 26.89 s | 22× | not recorded | 58 segments, 28.59% WER, cancellation |
| 21.2 min AMI | local native | 87.14 s | 14.6× | 1.10 GB | 29.24% WER |
| 84.9 min repeated AMI | local native | 226.39 s | 22.5× | 1.94 GB | 592 segments, 13 clusters for 5 speakers |
| 104.5 min six AMI | local native | 521.85 s | 12.0× | 2.49 GB | 603 segments, before memory fix |
| 104.5 min six AMI | local native | 404.80 s | 15.5× | 1.95 GB | bounded VAD, full PCM |
| 104.5 min six AMI | local native | **402.14 s** | **15.6×** | **1.82 GB** | bounded source + clustering, 143/603 flagged |

The 104.5-minute file concatenates six meetings; it is not one continuous
source recording. Throughput on a lower-powered laptop is unmeasured.

### Bounded source scaling

Paired in-process measurements with the same model and two threads:

| Duration | Bounded peak | Full-PCM peak |
|---|---:|---:|
| 10 min | 1,264.3 MB | 1,287.1 MB |
| 60 min | 1,350.3 MB | 1,459.2 MB |
| 104 min | 1,363.6 MB | 1,554.3 MB |
| 164.5 min | 1,356.8 MB | not measured |

Bounded input is flat from 60 minutes onward and produces identical SHA-256,
segments and duration to the full-PCM path. Compressed formats and
non-conforming WAV are decoded once to a private temporary WAV and then streamed;
the temporary file is removed. See `MEMORY_SCALING_20261125.md`.

## Blocking external decisions

1. **Distribution rights.** ERAIS runtime terms, LibriSpeech and GigaSpeech
   donor checkpoints, CAM++ donor terms and any TTS voice bank are not cleared
   for free community redistribution.
2. **Independent assessment.** No human or organisation outside the project has
   assessed the audio workflow, diarization or minutes.
3. **Signing/trust root.** The installer records digests but does not verify a
   publisher signature; production custody and rotation are unstaged.
4. **Cross-platform.** Only Linux x86-64 has been installed; Windows and macOS
   are unqualified.
5. **Hosted deployment.** Worker credentials and Cloudflare authentication are
   unrelated to the offline release but remain unset.

## What is safe to say publicly now

- Local, offline transcription works on Linux from a pinned source snapshot.
- Long recordings are admitted in bounded chunks and processed without a
  service, with measured throughput and memory on one desktop class machine.
- Anonymous speaker labels are experimental and reviewable; they are not
  identities.
- Draft minutes separate statements from established facts and go stale when a
  correction changes an outcome.

Nothing here establishes production quality on noisy meetings, a DER figure,
cross-platform support, or independent acceptance.
