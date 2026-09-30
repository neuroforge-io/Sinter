import assert from 'node:assert/strict';
import test from 'node:test';
import {registerReportDraft, trackReportEdits, trackReportEditor, reportEditorDraft,
  markReportSaved, unsavedReportDrafts, hasUnsavedReportDrafts, clearReportDrafts} from '../src/sinter/web/report-drafts.js';
import {hasPendingSource} from '../src/sinter/web/casebook-drafts.js';

test('applied and pending edits are separately retained until their exact content is saved', () => {
  clearReportDrafts();
  const report = {title: 'A fictional handover', incomplete: true, sources: [{content: 'No spending approved.'}]};
  registerReportDraft(report, 'Original draft');
  trackReportEditor(report, 'Pending draft');
  assert.equal(hasUnsavedReportDrafts(), true);
  assert.deepEqual(reportEditorDraft(report), {text: 'Pending draft', open: true});
  assert.equal(unsavedReportDrafts()[0].report, report);
  trackReportEditor(report, '', false);
  assert.equal(hasUnsavedReportDrafts(), false);
  trackReportEdits(report, 'Applied draft');
  trackReportEditor(report, 'Another pending draft');
  trackReportEditor(report, '', false);
  assert.equal(hasUnsavedReportDrafts(), true);
  markReportSaved(report, 'Applied draft');
  assert.equal(hasUnsavedReportDrafts(), false);
  assert.equal(report.incomplete, true);
  assert.equal(report.sources[0].content, 'No spending approved.');
});

test('a completed earlier save never clears edits made while it was pending', () => {
  clearReportDrafts();
  const report = {};
  registerReportDraft(report, 'Original');
  trackReportEdits(report, 'First edit');
  const transmitted = 'First edit';
  trackReportEdits(report, 'Second edit');
  markReportSaved(report, transmitted);
  assert.equal(hasUnsavedReportDrafts(), true);
  trackReportEditor(report, 'Third edit');
  markReportSaved(report, 'Second edit');
  assert.equal(hasUnsavedReportDrafts(), true);
  assert.equal(reportEditorDraft(report).text, 'Third edit');
  trackReportEditor(report, '', false);
  assert.equal(hasUnsavedReportDrafts(), false);
});

test('different reports with identical names do not merge; reopening preserves pending editor text', () => {
  clearReportDrafts();
  const a = {title: 'Same title'}, b = {title: 'Same title'};
  registerReportDraft(a, 'A'); registerReportDraft(b, 'B');
  trackReportEditor(a, 'A pending'); trackReportEdits(b, 'B edited');
  registerReportDraft(a, 'A');
  assert.equal(unsavedReportDrafts().length, 2);
  assert.equal(reportEditorDraft(a).text, 'A pending');
  markReportSaved(b, 'B edited');
  assert.equal(unsavedReportDrafts().length, 1);
  clearReportDrafts();
});

test('every pending source field counts, including whitespace and metadata-only entries', () => {
  assert.equal(hasPendingSource(), false);
  for (const key of ['title', 'content', 'date', 'url']) assert.equal(hasPendingSource({[key]: ' '}), true);
  assert.equal(hasPendingSource({title: '', content: '', date: '', url: ''}), false);
});
