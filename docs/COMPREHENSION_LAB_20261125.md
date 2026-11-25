# Sinter comprehension laboratory — 25 November 2026

## What changed

Sinter now has an actual application surface for the local ERAIS comprehension
service:

```text
#comprehension
    Teach an unfamiliar lesson
    Inspect the acquired concept
    Solve a hidden task
    Transfer the acquired capability to inventory, meeting or workspace context
    Observe, correct and clarify a persistent situation
```

The page is implemented in `src/sinter/web/comprehension.js` and is listed in
Sinter navigation as **Comprehension lab**.

Sinter does not parse lessons itself. `src/sinter/comprehension_bridge.py`
forwards only the allow-listed comprehension episode routes to a loopback HTTP
service configured by:

```sh
SINTER_COMPREHENSION_URL=http://127.0.0.1:8792
```

The bridge rejects non-loopback destinations, credential-bearing URLs and any
path outside `/api/comprehension/episodes*` or `/api/health`. Request and
response bodies are bounded.

## Cross-application witness

`tests/qualify_sinter_comprehension.py` starts the ERAIS comprehension API and
a Sinter server configured to proxy it. It teaches the lesson through Sinter,
transfers the capability, restarts Sinter, and transfers again:

```text
capability  capability:sha256:585ac5ac...e9beb8574
inventory   41 / reserve 9 -> 32
workspace   23 / reserve 7 -> 16
```

Receipt: `docs/audio/receipts/sinter_comprehension_20261125.json`

The receipt records the Sinter revision, comprehension service revision,
episode identity, state digest, page controls, transfer answers, capability
identity and separate process IDs.

## Verification

```text
tests/test_comprehension_bridge.py   3 passed
node --check comprehension.js         ok
node --check app.js                  ok
node --check navigation.js           ok
qualification                        status=qualified
```

## Limits

- The comprehension service is a separate local process. Sinter is a proxy and
  UI surface, not an in-process semantic engine.
- The bridge has no authentication or TLS; it binds to a local comprehension
  service.
- The lesson/situation grammars remain bounded.
- This is development qualification, not independent assessment.
