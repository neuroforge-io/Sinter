# Native model catalogue review — 18 October 2026

## Trigger and correction

A saved NeuroForge native selection with a 16-token answer cap was valid, but
**Load available models** failed with “max_tokens must be an integer from 32 to
8192.” Settings substituted a placeholder model during discovery; full-profile
validation then applied the legacy minimum to that placeholder.

Catalogue admission now validates the destination, API style and temporary
credential independently of generation settings. Settings sends only the
destination fields. Older four-field catalogue callers remain supported without
persisting or forwarding their model/cap fields into the catalogue context.

Full saves and generation retain their model, provider, identity and output-limit
checks. An ordinary model still cannot be saved with a 16-token cap. No model or
provider is selected automatically, and catalogue availability does not qualify
generation quality or compute availability.

## Evidence and boundaries

The source parent is b38f6b58a33b458b230759300a6a34c4c4e1ef4d.
The applied candidate's exact file hashes, original files, commands and outcomes
are retained in private operation receipts.

- 36 focused Python regressions passed, including native caps 1, 16 and 31,
  endpoint/style confirmation, held-key isolation, failure preservation and the
  real catalogue GET transport with a fictional opener.
- Nine Settings-page Node tests passed.
- 365 broader Python tests passed without skips: native setup, offline account
  isolation, native profile and the 57 public contract fixtures, provider
  transports/readiness/errors, and local profiles.
- Critical Python checks, explicit JavaScript module parsing with an invalid
  control, whitespace validation and the narrow public-boundary check passed.
- The actual in-app browser reopened the **same** fictional native-16 workspace
  used for the failing baseline. One catalogue lookup succeeded. The saved model
  and cap remained unchanged; no Save or generation action was taken. Original
  and final preference-file SHA-256 matched:
  589e0bf53d7acfb2c97dfffedd6a71becc5218aa3c933f7aa6d0da0a07c4d3f4.
  The single fixture catalogue call received destination fields without a model
  or cap. Hosted transport was blocked and was never attempted.
- The owned tab closed, the fixture server stopped and its thread was joined.
  The after-fix harness used 32,329,728 peak bytes and 0.315295 CPU seconds over a
  57.97-second operator session. These figures exclude the in-app browser and
  are not a customer latency benchmark.

The first after-fix harness attempt stopped before starting the application
because its transient service had the wrong working directory. Its failure
receipt remains retained. The corrected attempt used an explicit directory and
a fresh phase; no model request was replayed.

The existing quality-browser suite now includes the native-16 catalogue journey.
Its additional single-case headless invocation was not run locally: admission
was refused before process creation because the 1.125 GiB host-memory floor was
not met. The actual in-app browser journey above passed independently. The new
harness case remains unqualified until it executes.

No full browser-suite, installed-app, cross-platform or new release qualification
is claimed by this increment. The client, model profiles and public request and
response contract are unchanged. No credentials, private origins or model
downloads were used.

## Adversarial assessment

For this Settings workflow, the critic rated **user experience 6.5/10,
functionality 7/10 and aesthetics 7/10** after viewing both actual browser
screenshots and receiving the operation results. Those are scoped assessments;
they are not a whole-product rating.

The interface still asks users to understand model identifiers, token limits and
separate load/save/check actions. Successful discovery needs stronger completion
feedback, and the effective selected answer cap should be clearer.

Remaining defects are explicit:

- Late health/catalogue responses can still misrepresent a changed connection.
- A lost assistant-job acknowledgement still needs a clearer recovery path
  before the user can knowingly prepare another request.
- The separately measured mobile handover evidence visibility failure remains
  open; its 44-pixel target and 16-pixel inset checks have not been relaxed.

A successful catalogue lookup is a prerequisite, not a 10/10 experience.


## Offline guard and native fixture follow-up

An adversarial review of c1e916286bae49fe0c7c00e08e956b1470d52d34 found that
the quality harness's higher-level mocks did not guard legacy streaming's raw
HTTP path. The shared offline context now also blocks the raw client transport
and both standard-library urllib entry points, including account HTTP. Intended
fictional model fixtures remain above that boundary. Regressions exercise
captured streaming, raw transport and account aliases, direct urllib access,
intended fixture completion and restoration after failure.

The real native first-run CI journey also exposed a third outdated catalogue
fake using generation-only connection identity. It now asserts that catalogue
context has no model/cap, records only destination/provider and checks the exact
record. The unchanged one-call, original-report, explicit-model-choice,
source/export and restart assertions remain in place. No fallback model was
added to the client.

These follow-ups do not qualify the separately unrun headless native-catalogue
case, an installed release or the remaining Settings/assistant recovery flows.
