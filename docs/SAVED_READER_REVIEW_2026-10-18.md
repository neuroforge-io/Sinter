# Saved-report reader review - 18 October 2026

This is a bounded development-source review on parent
`b8fbd354d90ed5b1913872c99620e9c5ee8e4430`, not installed-release qualification.
The source version remains 0.5.4rc4; the published RC3 installer is unchanged.

## Result

Opening a saved report keeps its full title, collision-safe copy reference,
save state and document actions together. The named reading group receives
programmatic focus without adding a Tab stop. Tab enters Back to saved copies;
Back restores the saved-list filter. More retains the full reference, local
saved-copy check, deliberate duplication and the existing export controls.

An edit is saved as a new copy. Pending local inputs block omission from a save.
A new save after an uncertain outcome requires confirmation of the still-current
draft; it is never automatically replayed. In-flight status distinguishes the
submitted version from later edits. Earlier uncertain saves remain visible.

## Evidence and limits

- The final frozen development zipapp has SHA256
  `4a884de1594b592c6484abee260cf1bb01fc648a4405742d87637d750f97146f`.
  Its complete set of 144 source, notice and bootstrap entries was checked
  against the expected source set and contents.
- Actual in-app browser entry checks passed at 390 x 844 and 1265 x 712.
  The phone Back control was fully visible at y=11.125, with a 44-pixel height.
  Its first source target was 44 pixels high and ended at y=819.140625,
  leaving 24.859375 pixels below it. Title, identity, state and first action
  were visible without horizontal overflow. Keyboard entry, Back restoration,
  the full reference and the original Word options panel were checked.
- A preceding operator rehearsal edited one proposed action, saved exactly
  one additional local copy, cancelled deliberate duplication, and checked
  saved copies while retaining unapplied editor text. Database comparison
  preserved the original report and every unrelated table row; only the
  expected new report was added. Later changes adjusted presentation and focus.
- Final-source checks passed 139 JavaScript regressions, the Python entry point
  for the reader tests, explicit module parsing with an invalid-input control,
  critical Ruff checks and the public-boundary check. An earlier focused
  120-test Python run also passed; those Python implementation files are unchanged.
- Full local Chromium suites were refused by the host-memory admission gate.
  Their updated journeys still require fresh exact-commit CI. Harness changes
  for older installed candidates preserve the older control path; changing a
  harness does not qualify a new installed application.
- The final observed app phase quit normally, with no model-entry or blocked
  non-loopback socket attempts. Peak server/harness RSS was 40,759,296 bytes;
  browser-process memory is excluded. This is not machine-wide network isolation.
- Independent image review found no material visual blocker for this change:
  scoped UX 7.5/10, functionality 7.5/10 and aesthetics 7/10. Dense recorded-status
  wording, real uncertain-outcome interface evidence and installed qualification
  remain open. These are not whole-product scores.

Use the fictional garden bundle in `examples/offline-garden`. Original evidence,
unknown versus unassigned owners, unconfirmed dates and historical source wording
remain intact; this pass does not infer structured responsibility from old prose.

Fresh CI on `0dc4221` passed all three WASM browser jobs but exposed
two obsolete control locations in the deliverable journey. The follow-up
updates the three affected browser tools to reopen More before exact hidden
actions. Clipboard, recipient-privacy, pending-input, download and source
evidence assertions remain intact. This test-driver correction does not
change the product or establish an installed-app pass; fresh CI is required.

On `cf88016`, the mandatory saved-document journey passed. A later recovery
journey exposed an untouched prepared draft incorrectly expected to be edited.
The follow-up retains prepared state and exact visible content across navigation,
then checks pending state only after genuinely different wording is applied.
Quit protection and the remaining save/recovery assertions stay intact; fresh
CI is still required.

The first admitted local Chromium recovery probe reached the final JSON-restore
capture, then failed with a screenshot protocol error. It is not a suite pass;
checks after that capture had not run. The owned unit was collected, earlier
browser artifacts were unchanged, and its measured peak was 695,046,144 bytes
with no cgroup OOM event. Document height and memory are not established causes.
The follow-up moves a bounded viewport image after every exact restoration
check and records capture scope, DOM geometry and success separately. Capture
failure remains a failed run; earlier failure evidence is retained.

A subsequent admitted Chromium run passed all 22 offline report/source recovery
journeys with no external calls. It verified unchanged prepared content,
genuinely applied edits, uncertain-save and explicit-retry boundaries, JSON
restoration, original evidence and recovery of pending editor text. The run
completed in 43.8 seconds with about 9.1 cgroup CPU seconds and a measured peak
of 679,731,200 bytes, including the browser and harness, with no OOM event.
The final 1440-by-1000 image is explicitly a viewport witness; its sidecar
records geometry and successful capture. Earlier artifacts were unchanged,
the owned unit was collected and the runtime directory was removed.

Independent image review still found a tall, mostly empty editor that pushes
the recovered document below the viewport. The recovery pass does not remove
that usability finding or qualify an installed release. The Windows 3.13
registered-launcher fixture also missed its existing five-second deadline in
exact-`cf88016` CI; its cause remains unproven and the deadline is unchanged.

## Garden reading diagnostics after exact-4e CI

Exact `4e36334dbefbb3bafc9a76c0a830e6585699d5a8` CI passed the 22 recovery
journeys and the following document export, download-lifecycle and page-break
steps. The garden journey then failed its first-row visibility assertion.
The old tool wrote bounds only after both viewports passed, so that failure
does not identify the viewport, element or amount of overflow. Its original
failure artifact remains retained.

The follow-up probe flushes per-viewport geometry before the same assertions,
including reading position before More and after Escape. Failed geometry gains
a bounded viewport witness when capture succeeds. Secondary capture or evidence
write errors cannot replace the original assertion. No visibility threshold,
44-pixel target, evidence check or product layout was changed.

An admitted local Chromium run of that instrumented probe passed all 24 garden
practice journeys against unchanged exact-4e product source. It exercised the
paired offline project, original sources, explicit opening summary, Word export,
save/reopen and backup recovery, pending-input protection and stale-review
screen/print classifications. There were no browser errors or external requests;
earlier browser artifacts remained unchanged.

- Tool SHA256: `1f48436c0e4ffc01c8c78b90f878d4df8ed87585d59d77aefc6cb9499e87b4f8`.
- At 1265 by 712, the first action cell ended at y=583.75. At 390 by 844,
  the 44-pixel Passage target ended at y=807.765625, only 20.234375 pixels
  clear of the existing lower visibility bound at y=828. Before/after-More bounds matched
  locally. Loaded-font status does not prove the same font metrics as CI.
- The tool took 92.9 seconds including process/recovery observation, with 19.6
  cgroup CPU seconds and a peak of 680,828,928 bytes. Admission capped memory
  at 768 MiB, swap at zero and CPU at 25%; no OOM event occurred. The complete
  guarded phase closed in 97.1 seconds, reaped its child, collected the unit
  and removed its empty runtime directory.

This local pass does not resolve or classify the CI failure. Fresh CI must
retain its actual bounds before a layout fix is chosen. It is automated source
evidence, not a new installed-release or in-app operator qualification.

Exact-4e Windows 3.13 passed its unchanged launcher deadline; Windows 3.10
failed two fallback fixtures within that same five-second budget. The four
Linux/macOS Python lanes, RKC and three speech lanes passed. Verified packaging was
skipped. Historical Windows failures remain retained; their cause is not
established and no deadline was relaxed.

Independent review of the 390-by-844 image and these 24 offline journeys rates
this bounded path UX 7.5/10, functionality 8/10 and aesthetics 7.5/10.
The dense status paragraph still mixes status, owner, acceptance and target.
A future canonical action-section format should separate those facts while
preserving legacy tables literally; these scores do not cover the whole product.
