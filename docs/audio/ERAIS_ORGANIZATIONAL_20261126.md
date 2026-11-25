# ERAIS organizational interpretation for Sinter

**26 November 2026 | Sinter + ERAIS development qualification**

## Result

Sinter can now use ERAIS as the organizational semantic interpreter behind the
existing injection contract:

```text
SINTER_COMPREHENSION_URL=http://127.0.0.1:8792
SINTER_ORGANIZATIONAL_INTERPRETER=erais
```

ERAIS exposes:

```text
POST /api/organizational/interpret
```

It projects one reviewed passage into `sinter.organizational-event.v1`. Sinter
continues to own cross-passage motion chains, amount history, revision
comparison, claims and review status.

## Projection

ERAIS projects canonical tokenization, morphology and phrase structure into:

```text
motion
amendment
acceptance
responsibility
discussion
question
attendance
```

Each event carries:

```text
source_passage_id
source_speaker
evidence
actor
object
amount
due_date
outcome
source_claim_ids
semantic_graph_digest
projection = erais.canonical.organizational.v1
```

No event upgrades a stated agreement into formal approval. `confirmation_status`
remains `unconfirmed`.

## Qualification

Transcript:

```text
Alex  I propose we spend $600 on equipment.
Sam   Can we change that to $450?
Alex  Agreed.
Sam   I will order the equipment by Friday.
Alex  I propose we allocate $300 to training.
Sam   I propose we allocate $200 to signage.
Alex  We should review the training budget next month.
```

ERAIS scores against the independent gold events:

```text
event recall              1.0000
event precision           1.0000
participant accuracy      1.0000
evidence accuracy         1.0000
motion chain checks       7/7
correction history        $600 -> $425
stale motion/amendment    yes
```

Deterministic fallback on the same gold set:

```text
event recall              0.2857
event precision           0.2857
```

The fallback remains available and is still the default unless explicitly
selected.

Correction witness:

```text
original amendment        $450
corrected amendment       $425
motion amount history     $600, $425
stale claims              motion, motion_amendment, financial
```

## Receipt

```text
docs/audio/receipts/erais_organizational_20261126.json
status: qualified
```

Pins are recorded in the receipt for both the ERAIS and Sinter revisions.

## Verification

```sh
cd /home/lloyd/sinter
python3 tests/qualify_erais_organizational.py
python3 -m pytest -q tests/test_organizational_interpreter.py \
  tests/test_comprehension_bridge.py tests/test_meeting_semantics.py \
  tests/test_meeting_claims.py
```

```text
22 passed
```

## Limits

- The projection is bounded to explicit organizational predicates, typed
  amounts, deadlines and participant phrases.
- Sinter still composes motions and revisions; ERAIS does not own the final
  minutes.
- The local comprehension service has no independent principal authorization
  beyond the loopback boundary and Sinter authentication.
- Formal approval, attendance, identity and vote outcomes remain human review
  obligations.
- No independent assessor has reviewed this increment.
