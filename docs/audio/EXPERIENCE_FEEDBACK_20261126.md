# Sinter correction feedback to ERAIS

**26 November 2026 | Development qualification**

Sinter sends verified human transcript corrections to the local ERAIS experience
ledger when explicitly enabled:

```sh
SINTER_EXPERIENCE_FEEDBACK=erais
SINTER_COMPREHENSION_URL=http://127.0.0.1:8792
```

The adapter is `src/sinter/experience_feedback.py`. It posts one recognition
correction with:

```text
category: recognition
learning_scope: organization
scope_id: meeting:<digest>
verification: human transcript review
source_revision: SINTER_SOURCE_REVISION
```

Sinter's minutes result now includes `experience_receipts`. Corrections are
candidates only; no model training or scope promotion occurs.

```text
tests/test_experience_feedback.py        4 passed
tests/test_comprehension_bridge.py       3 passed
```

The shared qualification runner is in the Workspace repository at
`tests/qualify_learning_feedback.py`.
