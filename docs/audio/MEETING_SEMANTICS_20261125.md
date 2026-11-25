# Cross-passage organizational semantics — 25 November 2026

## What changed

Draft minutes no longer derive their primary claims from independent keyword
patterns. `src/sinter/meeting_semantics.py` now builds typed organizational
events and composes them across passages:

```text
passage
    → clause-level events
        motion / amendment / acceptance
        responsibility / deadline
        budget / attendance / question / discussion
    → motion chain
        original proposal amount
        linked amendments and amounts
        linked acceptance evidence
        linked responsibility and deadline
    → reviewable claims
```

Each event and claim keeps its source passage, speaker, timestamp, evidence text,
`assertion_status = stated`, `confirmation_status = unconfirmed`, related event
identities and semantic roles. A motion remains a proposal. "Agreed" or "that
works" is recorded as `stated_agreement`, never as formal approval.

The semantic interpreter is injectable:

```python
analyze(passages, interpreter=era_is_interpreter)
```

An ERAIS interpreter can supply the same `sinter.organizational-event.v1`
events. The deterministic interpreter in this module is the local fallback and
test fixture; it is not another lexical authority.

## Composition examples

```text
Alex: We should allocate $600 for the replacement equipment.
Sam: Can we make that $450 instead?
Alex: Yes, that works.
Chris: I'll organize the purchase before Friday.
```

produces:

```text
motion E0001:motion:01       $600
budget E0001:budget:01       $600
amendment E0002:amendment:01 $450, motion=E0001:motion:01
budget E0002:budget:01       $450
acceptance E0003:acceptance:01 stated_agreement, motion=E0001
responsibility E0004          actor=Chris, action=organize the purchase
due_date                      Friday, linked to the responsibility
motion chain                  $600 -> $450; acceptance=stated_agreement
```

## Correction propagation

The repository is analyzed twice when corrections exist: original text and
corrected text. Event identities are stable per passage/type/ordinal, and field
differences are compared. Claims are marked stale only for their own changed
event or a directly relevant motion-chain change:

| Correction | Stale | Remains current |
|---|---|---|
| `$600` → `$550` in the proposal | motion, proposal budget | amendment, later budget, decision, responsibility |
| `$450` → `$300` amendment | motion, amendment, amendment budget | proposal budget, decision |
| responsibility `Chris` → `Michael` | action, deadline | motion, budgets, amendment, decision |
| `Yes, that works` → `We discussed it but did not agree` | motion acceptance, discussion | budgets, responsibility |

Wording-only edits that preserve the action verb and object head do not stale a
claim merely because an adjective changed.

## Evidence

```text
tests/test_meeting_semantics.py   6 passed
tests/test_meeting_claims.py      6 passed
tests/test_meeting_source_snapshot.py  25 passed
```

The tests cover amended motions, changed responsibility, amendment/amount
propagation, acceptance removal, injected semantic events and the original
truthfulness/consent behaviour.

## Limits

- The local fallback interpreter is deterministic and conservative; it is not an
  independently trained semantic model.
- The ERAIS interpreter contract is implemented at the Python callable boundary;
  no ERAIS semantic endpoint is configured by default.
- Formal approval, quorum, attendance and official vote outcomes remain human
  review obligations. The event layer must not manufacture them.
- Meeting-local speaker labels remain anonymous unless a reviewer maps them.
