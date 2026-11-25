# Evidence-grounded meeting claims — 25 November 2026

## What changed

Draft minutes now carry structured claim records in addition to the existing
keyword candidates. The record separates:

```text
what a participant said        assertion_status = "stated"
what the transcript supports   evidence_status = "transcript_only"
what a human confirmed         confirmation_status = "unconfirmed"
what a correction invalidated  claim_status = "stale"
```

Types recognised from explicit keywords or values: `motion`, `vote`,
`decision`, `action`, `attendance`, `financial`, `due_date`, `question`.
A passage can produce several records.

Each record keeps `claim_id`, quote, source passage, source speaker, source
clock and the extraction evidence. Nothing is inferred as passed, approved,
attended or paid.

## Revision-aware invalidation

When a reviewer correction changes outcome words (`carried`/`not carried`,
`approved`/`rejected`, `pending`, `withdrawn`, ...) or a monetary amount, every
claim from that passage becomes `stale` with
`reinterpretation_required: true`, and the original and corrected sentences are
retained in `transcript_revision`. Wording-only corrections keep the claim
current but still record the revision.

The draft minutes render both a candidate-claims section and a
"Claims invalidated by transcript revision" section. The JSON result exposes
the same records, so exports do not need a second interpretation.

## Limits

- Claims are keyword candidates, not semantic interpretation. Agent A's
  predicate and quantity interpretation should replace the pattern layer.
- Confirmation is currently a record field; there is no chair-approval workflow
  that sets it to `confirmed`.
- Attendance is only a stated mention, never inferred from a speaker label.
- Export formats other than the minutes Markdown/JSON do not yet project the
  claim table.

## Verification

```text
tests/test_meeting_claims.py            6 passed
meeting + runtime + workbench suites  109 passed
```
