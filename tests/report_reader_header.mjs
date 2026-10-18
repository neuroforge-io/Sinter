import test from 'node:test';
import assert from 'node:assert/strict';
import {registerReportDraft, rememberReportSavedCopy, markReportSaving, markReportSaved,
  markReportSaveFailed, trackReportEdits, trackReportEditor, trackReportForm,
  clearReportForm, reportSavingHasNewerEdits, clearReportDrafts} from '../src/sinter/web/report-drafts.js';
import {readerSavePresentation, authorizeAdditionalReportCopy} from '../src/sinter/web/report-reader-header.js';

const id = 'a'.repeat(32), secondId = 'b'.repeat(32);
function savedReport() {
  clearReportDrafts();
  const report = {title: 'Fictional handover', markdown: 'Original wording', sources: []};
  registerReportDraft(report, report.markdown, {saved: true});
  rememberReportSavedCopy(report, id);
  return report;
}
test('an unchanged acknowledged copy has no prominent save action and keeps its complete identity', () => {
  const report = savedReport(), before = JSON.stringify(report);
  const view = readerSavePresentation(report);
  assert.equal(view.id, id); assert.equal(view.identityLabel, 'Saved copy');
  assert.equal(view.saveHidden, true); assert.equal(view.duplicateHidden, false);
  assert.equal(JSON.stringify(report), before);
});
test('applied edits retain the last acknowledged identity and offer an append-only save', () => {
  const report = savedReport();
  report.markdown = 'New reviewed wording'; trackReportEdits(report, report.markdown);
  const view = readerSavePresentation(report);
  assert.equal(view.id, id); assert.equal(view.identityLabel, 'Last acknowledged copy');
  assert.equal(view.kind, 'pending'); assert.equal(view.saveLabel, 'Save new copy');
  assert.equal(view.saveDisabled, false); assert.equal(view.duplicateHidden, true);
});
test('every unapplied local form and editor blocks a save without discarding inputs', () => {
  const report = savedReport();
  trackReportForm(report, 'future-extension-form', {owner: 'unknown'});
  assert.equal(readerSavePresentation(report).saveDisabled, true);
  clearReportForm(report, 'future-extension-form');
  trackReportEditor(report, 'Unapplied wording');
  assert.equal(readerSavePresentation(report).saveDisabled, true);
});
test('save progress describes the exact submitted version and never marks later edits saved', () => {
  const report = savedReport();
  report.markdown = 'Submitted version'; trackReportEdits(report, report.markdown);
  const submitted = structuredClone(report);
  markReportSaving(report, submitted, submitted.markdown);
  assert.equal(reportSavingHasNewerEdits(report), false);
  assert.equal(readerSavePresentation(report).summary, 'Saving a new copy...');
  report.markdown = 'Later version'; trackReportEdits(report, report.markdown);
  assert.equal(reportSavingHasNewerEdits(report), true);
  assert.match(readerSavePresentation(report).summary, /earlier version.*Newer edits/);
  markReportSaved(report, submitted.markdown, submitted, secondId);
  const view = readerSavePresentation(report);
  assert.equal(view.kind, 'pending'); assert.equal(view.id, secondId);
  assert.equal(view.identityLabel, 'Last acknowledged copy'); assert.equal(view.saveDisabled, false);
});
test('an uncertain older save is not hidden by a later rejection or acknowledged copy', () => {
  const report = savedReport();
  markReportSaveFailed(report, {});
  assert.equal(readerSavePresentation(report).kind, 'unconfirmed');
  assert.match(readerSavePresentation(report).summary, /unknown.*Check saved/);
  markReportSaveFailed(report, {requestState: {outcome: 'rejected'}});
  assert.match(readerSavePresentation(report).warning, /earlier save remains unconfirmed/);
  markReportSaved(report, report.markdown, report, secondId);
  const view = readerSavePresentation(report);
  assert.equal(view.kind, 'saved'); assert.equal(view.id, secondId);
  assert.match(view.warning, /additional copy may exist/i);
});
test('cancelled or inactive additional-copy decisions cannot grant a write', async () => {
  const report = savedReport(); let decisions = 0;
  assert.deepEqual(await authorizeAdditionalReportCopy(report, {
    isActive: () => false, confirm: async () => { decisions++; return true; },
  }), {allowed: false, reason: 'inactive'});
  assert.equal(decisions, 0);
  assert.deepEqual(await authorizeAdditionalReportCopy(report, {
    confirm: async () => false,
  }), {allowed: false, reason: 'cancelled'});
});
test('an exact additional-copy confirmation cannot authorise newer text, records or forms', async () => {
  for (const mutate of [
    report => { report.markdown = 'Newer wording'; trackReportEdits(report, report.markdown); },
    report => { report.sources.push({id: 'retained-later', content: 'Different retained record'}); },
    report => { trackReportForm(report, 'future-extension-form', {date: 'unconfirmed'}); },
  ]) {
    const report = savedReport();
    const result = await authorizeAdditionalReportCopy(report, {confirm: async () => { mutate(report); return true; }});
    assert.deepEqual(result, {allowed: false, reason: 'changed'});
  }
});
test('a save begun elsewhere or a disposed view cannot use an earlier decision', async () => {
  const report = savedReport(); let active = true;
  const result = await authorizeAdditionalReportCopy(report, {
    isActive: () => active, confirm: async () => { active = false; return true; },
  });
  assert.deepEqual(result, {allowed: false, reason: 'inactive'});
  markReportSaving(report);
  assert.deepEqual(await authorizeAdditionalReportCopy(report, {
    confirm: async () => { throw Error('must not ask while saving'); },
  }), {allowed: false, reason: 'saving'});
});
test('an exact active explicit confirmation leaves persistence to the existing caller', async () => {
  const report = savedReport(), before = JSON.stringify(report);
  assert.deepEqual(await authorizeAdditionalReportCopy(report, {confirm: async () => true}), {allowed: true});
  assert.equal(JSON.stringify(report), before);
});
