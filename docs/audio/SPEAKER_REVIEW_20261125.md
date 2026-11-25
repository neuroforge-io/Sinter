# Usable speaker review — 25 November 2026

## What changed

The transcript review panel now exposes the information a reviewer needs to
judge an anonymous cluster, and every correction is reversible:

- each group shows passage count and **speaking duration**;
- **Listen to a passage** seeks the recording to the group's longest
  unflagged passage;
- **Merge groups** reassigns every passage of one group into another;
- **Undo last speaker change** reverts the most recent group rename, merge or
  single-passage relabel;
- every operation appends a `speaker_revisions` record with `revision_id`,
  `operation`, `from`, `to`, affected `segment_indices`, the previous label per
  passage, the previous revision, an optional reason, and `undone` when
  reverted;
- the JSON transcript carries the full revision history; SRT/VTT/TXT remain
  projections of the accepted labels.

Machine labels remain traceable through `original_speaker` and the revision
ledger. A merge never invents a named identity; it only changes the display
label.

## Limits

- Revisions are session-side until the transcript is saved through the existing
  meeting/project flow; they are not a durable database table yet.
- There is no split operation that partitions a passage by time; review can
  relabel passages but not sub-passage turns.
- Representative audio is the longest unflagged passage, not an acoustic
  quality-ranked clip with a similarity score.
- No biometric template or embedding is exported.

## Verification

```text
node --test tests/transcription_speaker_groups.mjs   5 passed
node --input-type=module --check < transcription.js  ok
```
