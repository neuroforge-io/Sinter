# Workbench recovery review — 30 September 2026

These changes are subsequent `0.5.4rc2.dev0` development. The Linux preview
`0.5.4rc1` remains frozen at
`cd928ba7561a09c477b3555e64aa6a3c4cc122b4`; its installers and installed-app
qualification do not include these changes.

## Failures reproduced and corrected

| Operator action | Previous failure | Current behavior |
| --- | --- | --- |
| Paste a source, then change pages | The unadded text disappeared without an exit warning. | Title, text, date and link remain in the session. Add or explicitly clear the pending source before saving, preparing or exporting the project. |
| Edit a handover, save project inputs, then change pages | The report edit disappeared, while saving the project misleadingly cleared the dirty state. | Applied edits and unfinished editor text appear in My workspace. Project and document saves have independent state. Exit warns until document edits are saved or deliberately discarded. |
| Edit action-plan inputs after preparation | Downloads and Save still used the preceding plan. | The preceding result stays visible, but its export/save controls become unavailable. Explicitly prepare the revised inputs before exporting them. |

A save records the exact snapshot transmitted. Editing while a save is pending
does not mark newer text saved. A failed save keeps the edits and offers explicit
retry. Reopening session edits retains the original inputs, source hashes,
excerpts and incomplete status, and warns that later project changes are not
part of the earlier preparation. None of these paths replays a model request.

Session recovery is not crash recovery: unapplied or unsaved edits still require
**Apply edits → Save to My workspace** before closing the browser or app. The
exit warning makes this limit visible; saving project inputs does not save a
document. Nothing is uploaded or sent automatically.

**Save to My workspace** is the current development label. The published
0.5.4rc3 preview calls this same report action **Save to this computer**.
Saving a Word copy is a separate file operation.

## Actual operator evidence

The browser run used an isolated fictional workspace. The operator pasted a
supplier note, changed pages, recovered it, encountered the pending-source save
guard, explicitly added it, and prepared a local volunteer handover. The operator
then rewrote the handover, recovered those edits through My workspace, saved the
document, closed the browser tab, stopped the server, started a fresh process,
and reopened the saved document. Its edited wording and original evidence were
both present, including “No order has been approved.”

The report now receives focus and scrolls into view when preparation completes.
Independent measurement at a 1,440 × 1,000 viewport moved the report heading
from below the viewport at 1,168 pixels to 269 pixels after preparation.

Retained local evidence, excluded from product packages:

- `browser-artifacts/report-recovery-summary.json`: eight recovery journeys,
  including failed saves, pending editor recovery and edits during a held save.
- `browser-artifacts/community-recovery-summary.json`: ten plan journeys,
  including changed inputs, preparation races, validation failure, downloads
  and saved reopening.
- `browser-artifacts/recovery-independent-review/`: independent reproduction
  and closure receipts for the three reported failures.
- `browser-artifacts/recovered-handover-human-reopened.jpg`: the saved handover
  reopened after a complete process restart.

The source/browser checks do not substitute for qualifying a newly built native
installer. The previously frozen candidate's installed qualification remains
separate in `browser-artifacts/final-independent-qualification/`.

## Validation and measured scope

The completed recovery checkpoint passed 1,511 Python tests (five skipped),
108 JavaScript tests, both new browser suites and the existing casebook, studio,
campaign and desktop browser checks. Public-boundary checks and the deterministic
offline self-audit passed. The five Python skips remain skips, not passes.

`tools/offline_benchmark.py` measured warm local casebook preparation on this
Linux x64 / Python 3.12.3 machine:

| Workload | Samples | Median | Maximum |
| --- | --- | --- | --- |
| Agreed fictional garden, four documents / 2,278 characters | 15 | 0.47 ms | 0.78 ms |
| Synthetic sizing, 300 documents / 1,980,000 characters | 3 | 173.98 ms | 174.93 ms |

Both results retained literal, validated excerpts. The large synthetic result
selected three passages from two documents and explicitly disclosed the other
298 unrepresented documents. Its separately instrumented traced allocation peak
was 5,284,533 bytes. The cumulative profile identified text admission/validation
as the largest component. The receipt includes fixture and implementation hashes.
These measurements describe local preparation only: they do not measure browser
responsiveness, model quality or hosted capacity. No external requests occurred.

## Adversarial assessment

The independent reviewer closed all three concrete recovery findings and found
no remaining P1/P2 in the bounded recovery journeys. Their current subjective
ratings are UX **7.6**, functionality **8.2**, aesthetics **7.5**. They are not
whole-product acceptance or a 10/10 claim. The next visible deficiencies are
discovery of the complete garden example, a long casebook intake form, and weak
distinction between same-title recovery entries.
