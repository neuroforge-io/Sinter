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
