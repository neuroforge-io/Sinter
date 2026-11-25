# Evidence-specific review triage — 25 November 2026

Previously every local meeting passage carried the same warning, so a 104-minute
recording reported `review_count = 603/603`. That cannot guide a reviewer.

Flags are now raised only for concrete reasons:

| Evidence | Flag |
|---|---|
| Speaker assignment marked overlap | Multiple people may be speaking |
| Anonymous cluster uncertain | Confirm the speaker |
| Number, currency or percentage | Check the amount, date or number |
| Negation words | Check negation |
| Decision/obligation words | Confirm the decision wording |
| >0.1% samples at full scale | Distorted audio: clipped |
| Speech region below -45 dBFS | Difficult to hear |

The generic "check names, amounts, negation and unclear words" reminder stays at
transcript level as a warning, not as a per-passage flag. Speaker labels remain
a separate review axis.

## Limits

- The native recognizer does not expose word probabilities, so there is no
  low-confidence flag yet; adding calibration is a recognition-side task.
- Clipping and level are computed per VAD region from the original PCM.
- Numbers and negation are lexical hints, not semantic verification.
- `review_count` counts passages with at least one flag; a passage may carry
  several.

## Observed effect

On a 30 s AMI mixed-headset MP3 through the installed desktop worker:

```text
before: 5/5 passages flagged with the same generic warning
after:  0/5 flagged
```

The excerpt is uniformly quiet (whole-file mean -52.6 dB, peak -28.8 dB, RMS
-41 dBFS), which is exactly the case an absolute quiet threshold handles
badly. The 1 h 44 min receipt in `MULTIHOUR_QUALIFICATION_20261125.md`
reported `review_count = 603` under the old rule; that number is historical and
does not represent consequential risk. After the change, the same recording
reports **143/603** flagged passages, with the other 460 passages still
reviewable but not pre-flagged.

## Verification

```text
tests/test_sinter_longform.py   18 passed
  including money/negation/clipping/quiet/overlap cases
```
