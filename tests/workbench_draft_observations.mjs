import assert from 'node:assert/strict';
import test from 'node:test';
import {createWorkbenchDraftObservations} from '../src/sinter/web/workbench-draft-observations.js';
import {registerReportDraft, trackReportEditor, trackReportEdits, trackReportForm, clearReportForm,
  reportSaveState, reportEditorDraft, markReportSaving, markReportSaved, markReportSaveFailed,
  reportReplacementState, reportReplacementUnchanged, clearReportDrafts} from '../src/sinter/web/report-drafts.js';

test('only the changed draft is read; unchanged input and cached reads do no badge work', () => {
  clearReportDrafts();
  const reports = [{title: 'A'}, {title: 'B'}, {title: 'C'}], reads = new Map();
  let changes = 0;
  const view = createWorkbenchDraftObservations({
    isActive: () => true, onChange: () => { changes++; },
    readSaveState: report => {
      reads.set(report, (reads.get(report) || 0) + 1); return reportSaveState(report);
    },
  });
  for (const [index, report] of reports.entries()) {
    registerReportDraft(report, 'Original', {saved: true});
    view.add({number: index + 1, report});
  }
  reads.clear();
  trackReportEditor(reports[0], 'Pending A');
  assert.equal(changes, 1); assert.equal(reads.get(reports[0]), 1);
  assert.equal(reads.has(reports[1]), false); assert.equal(reads.has(reports[2]), false);
  assert.equal(view.get(1).save.kind, 'pending'); assert.equal(view.get(1).pendingText, true);
  assert.equal(view.get(2).save.kind, 'saved'); assert.equal(view.get(3).save.kind, 'saved');
  trackReportEditor(reports[0], 'Pending A'); view.get(1); view.get(2);
  assert.equal(changes, 1); assert.equal(reads.get(reports[0]), 1);
  view.dispose();
});

test('each edit/form/save outcome refreshes the right snapshot and keeps uncertainty literal', () => {
  clearReportDrafts(); const report = {};
  registerReportDraft(report, 'Original', {saved: true});
  const kinds = [];
  let view;
  view = createWorkbenchDraftObservations({
    isActive: () => true, onChange: () => kinds.push(view.get(1).save.kind),
  });
  view.add({number: 1, report});
  trackReportEdits(report, 'Applied');
  trackReportForm(report, 'handover-summary', {rows: ['Unassigned']});
  clearReportForm(report, 'handover-summary');
  markReportSaving(report); markReportSaveFailed(report, {requestState: {outcome: 'not-sent'}});
  markReportSaving(report); markReportSaveFailed(report, {requestState: {outcome: 'rejected'}});
  markReportSaving(report); markReportSaveFailed(report, {requestState: {outcome: 'unconfirmed'}});
  trackReportEditor(report, 'Pending text');
  assert.equal(view.get(1).save.kind, 'unconfirmed'); assert.equal(view.get(1).pendingText, true);
  markReportSaved(report, 'Applied', structuredClone(report));
  assert.equal(view.get(1).save.kind, 'pending'); assert.equal(view.get(1).pendingText, true);
  assert.deepEqual(kinds, ['pending', 'pending', 'pending', 'saving', 'not-sent', 'saving',
    'rejected', 'saving', 'unconfirmed', 'unconfirmed', 'pending']);
  view.dispose();
});

test('a delayed acknowledgement updates an earlier draft without clearing its newer text', () => {
  clearReportDrafts(); const a = {}, b = {};
  registerReportDraft(a, 'A'); registerReportDraft(b, 'B');
  const view = createWorkbenchDraftObservations({isActive: () => true, onChange: () => {}});
  view.add({number: 1, report: a}); view.add({number: 2, report: b});
  const submitted = structuredClone(a); markReportSaving(a);
  trackReportEditor(a, 'A later edit'); markReportSaved(a, 'A', submitted);
  assert.equal(view.get(1).save.kind, 'pending'); assert.equal(view.get(1).pendingText, true);
  assert.equal(view.get(2).save.kind, 'prepared');
  assert.equal(reportEditorDraft(a).text, 'A later edit');
  view.dispose();
});

test('snapshot failure, missing entries and disposed observations never promise a saved draft', () => {
  clearReportDrafts(); const report = {};
  registerReportDraft(report, 'Original', {saved: true});
  let fail = false, active = true, changes = 0, reads = 0;
  const view = createWorkbenchDraftObservations({
    isActive: () => active, onChange: () => { changes++; },
    readSaveState: value => {
      reads++; if (fail) throw new Error('Fictional snapshot read failure'); return reportSaveState(value);
    },
  });
  view.add({number: 1, report}); assert.equal(view.get(1).save.kind, 'saved');
  fail = true; trackReportEdits(report, 'Changed');
  assert.equal(view.get(1).save.kind, 'unknown'); assert.equal(view.get(2).save.kind, 'unknown');
  const known = reads; view.dispose(); trackReportEditor(report, 'Later');
  assert.equal(reads, known); assert.equal(changes, 1);
  assert.equal(view.get(1).save.kind, 'unknown'); assert.equal(view.add({number: 2, report}), false);
  const inactive = createWorkbenchDraftObservations({isActive: () => active, onChange: () => {}});
  active = false; assert.equal(inactive.add({number: 3, report}), false); inactive.dispose();
});

test('presentation has no authority to approve replacement and numbers cannot merge reports', () => {
  clearReportDrafts(); const a = {}, b = {};
  registerReportDraft(a, 'Original', {saved: true}); registerReportDraft(b, 'B');
  const view = createWorkbenchDraftObservations({isActive: () => true, onChange: () => {}});
  view.add({number: 1, report: a});
  assert.throws(() => view.add({number: 1, report: b}), /another report/);
  const before = reportReplacementState(a);
  // An untracked external mutation deliberately leaves the last-observed badge stale.
  a.changed = 'New retained record';
  assert.equal(view.get(1).save.kind, 'saved');
  assert.equal(reportReplacementUnchanged(a, before), false);
  view.refresh(1); assert.equal(view.get(1).save.kind, 'pending');
  assert.equal(Object.isFrozen(view.get(1)), true);
  view.dispose();
});
