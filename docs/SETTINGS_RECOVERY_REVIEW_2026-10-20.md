# Settings recovery source review — 20 October 2026

This is a bounded source improvement based on main
`18a63ca3bdaee1df1e73bf39a25797258fc1d302`. It does not qualify an
installer, a hosted model, every account operation or the whole product.

## Behavior

The local app Settings page sends the revision it observed with Save connection,
Save my preferences and Forget the session API key. Preferences compares that
opaque token under its existing lock before changing the file or held key.
A mismatch returns 409. Settings, key-presence flag and revision are captured
together; each successful update advances the revision, including key-only and
no-op updates. A restart creates a new revision. The file format is unchanged:
neither the runtime revision nor the session key is written into preferences.

Preconditions are optional for existing callers. Omitting one retains legacy
behavior; explicitly null or malformed values are rejected. Legacy requests
without a precondition do not receive the new concurrency protection.

Forget submits only an empty settings patch and an empty held key. It cannot
write an old full profile back over a successful save. Acknowledgements advance
the saved baseline without replacing newer form inputs. Save clears a typed key
only when that key has not been edited since submission; Forget leaves any typed
replacement alone. Save connection submits only the four connection fields.
Invalid unsaved email or RKC fields do not block that action, and profile,
appearance and RKC drafts require Save my preferences.

An incomplete or malformed successful acknowledgement remains unconfirmed.
Conflicting or unconfirmed writes block further settings mutations until the
operator chooses Check what was saved. That GET observes the current revision;
it does not establish that an earlier request stopped or failed. Earlier
uncertainty remains visible. A subsequent explicit revision-aware write cannot
share a successful revision with an older delayed write. No write is replayed.

Health and catalogue observations use independent handles and a connection
generation. Changes invalidate earlier successes, failures, finalizers and
catalogue-choice listeners, including A → B → A. An unchanged health check and
catalogue lookup can complete in either order. Health replies identify the
preferences revision captured with their actual connection. The anonymous browser
runtime captures the same metadata without enabling credentials or providers.
Catalogue discovery does not select, save or generate anything.

Account mutations share the active-request controls with settings writes.
Older account reads cannot override a later mutation; retained completed sign-in
records do not reset an explicitly staged account choice. This does not add
backend revision protection or complete unknown-outcome recovery to accounts.

## Evidence

- Initial focused Python run: **152 passed**, covering revision races, lost
  acknowledgements, key-only/no-op changes, restart conflicts, malformed
  preconditions, disk failure, atomic acknowledgements, real loopback HTTP,
  provider isolation and native profiles.
- Actual-page JavaScript and provider policy tests: **33 passed**, zero cancelled
  or skipped after correcting an explicit-model fixture. Cases cover delayed
  health/catalogue responses, detached choices, newer drafts, malformed/unusable
  acknowledgements, readback, partial Forget and account-read fences.
- Critical Ruff, Python AST, exact module parsing with an invalid-input control,
  whitespace and the narrow public-boundary check passed.
- A manual in-app-browser rehearsal used one fictional local workspace and the
  real server. An older availability response was held across A → B → A.
  A real save was committed while its acknowledgement waited, allowing a newer
  cap and key draft. Another real save returned deliberately incomplete JSON;
  the interface retained uncertainty and required explicit readback.
- The rehearsal made exactly three settings writes: two connection patches and
  one empty settings patch for Forget. Native cap 16, the empty saved profile and
  dark saved theme survived. An invalid unsaved email and a light-theme draft
  were not saved by Save connection.
- Two destination-only catalogue requests retained explicit native selection.
  There were **zero model or external transport attempts**. Health was an
  explicitly fictional availability fixture, not hosted generation.
- The replacement password remained visibly populated, but browser DOM inspection
  redacts password values. Exact key-value preservation is established by the
  targeted JavaScript cases, not by a browser equality probe.
- Desktop and 390 × 844 phone screenshots were retained. The phone had no
  horizontal overflow; the four inspected action targets were 44.5 pixels high.
  The owned tab closed, its viewport override reset, the controlled server
  stopped, handlers drained and the server thread was reaped. The real default
  workspace preferences stayed unchanged.
- The bounded server/controller closed successfully after 165.97 seconds.
  Its 192 MiB limit excluded the existing browser; collected-unit peak memory
  was unavailable. This is an operational receipt, not a speed benchmark.

An additional adapter/profile group passed **79 Python cases**, including
anonymous health success/failure and the common browser-domain exercise.
A further **6 HTTP/shared-runtime settings/health cases passed** (95 unrelated
cases deselected). These groups overlap the earlier focused group; their counts
are not presented as unique tests. The common exercise is also used by the
Pyodide browser CI lanes, but this local execution used CPython. Fresh exact-source
Pyodide/Chromium/Firefox/WebKit results remain pending.

## Remaining work

Independent review of the rendered Settings slice rated UX **6.5/10**,
functionality **7.5/10**, aesthetics **6.5/10**. These are scoped judgements,
not product qualification. The next improvements should put the effective
16-token cap before the 128-token ceiling, distinguish an unsaved replacement
key from the held key, shorten duplicate uncertainty messages, make catalogue
success quieter, and simplify the optional public-preview key field.

Account mutation interruption recovery, the separate browser-only settings
editor, and installed upgrade/release qualification remain open. The preceding
main CI run failed the existing narrow-screen handover evidence-control gate.
That layout failure is not repaired or waived by this change. Fresh exact-source
CI is still required; successful source tests are not an installed release.
