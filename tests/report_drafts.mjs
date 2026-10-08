import assert from 'node:assert/strict';
import test from 'node:test';
import {registerReportDraft, trackReportEdits, trackReportEditor, reportEditorDraft,
  markReportSaved, markReportSaving, markReportSaveFailed, reportSaveState, observeReportSaveState,
  trackReportForm, clearReportForm, unsavedReportDrafts, hasUnsavedReportDrafts, clearReportDrafts} from '../src/sinter/web/report-drafts.js';
import {hasPendingSource} from '../src/sinter/web/casebook-drafts.js';

test('applied and pending edits are separately retained until their exact content is saved', () => {
  clearReportDrafts();
  const report = {title: 'A fictional handover', incomplete: true, sources: [{content: 'No spending approved.'}]};
  registerReportDraft(report, 'Original draft', {saved: true});
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

test('a matching baseline, title or report ID never establishes a persisted report', () => {
  clearReportDrafts();
  const report = {id: 'fictional-saved-looking-id', title: 'Saved-looking name'};
  const before = structuredClone(report);
  assert.equal(reportSaveState(report).kind, 'unknown');
  registerReportDraft(report, 'Prepared locally');
  assert.equal(reportSaveState(report).kind, 'prepared');
  assert.match(reportSaveState(report).message, /not saved/);
  assert.equal(hasUnsavedReportDrafts(), true);
  assert.equal(unsavedReportDrafts()[0].report, report);
  assert.deepEqual(report, before);
});

test('only explicit persisted context or an acknowledged save establishes saved state', () => {
  clearReportDrafts();
  const fetched = {}, prepared = {}, invalid = {};
  registerReportDraft(fetched, 'Fetched saved copy', {saved: true});
  registerReportDraft(invalid, 'Prepared', {saved: 'true'});
  registerReportDraft(prepared, 'Prepared');
  assert.equal(reportSaveState(fetched).kind, 'saved');
  assert.equal(reportSaveState(invalid).kind, 'prepared');
  registerReportDraft(prepared, 'Prepared', {saved: true});
  assert.equal(reportSaveState(prepared).kind, 'prepared'); // Re-render does not reset local observations.
  markReportSaving(prepared);
  assert.equal(reportSaveState(prepared).kind, 'saving');
  markReportSaved(prepared, 'Prepared');
  assert.equal(reportSaveState(prepared).kind, 'saved');
});

test('an unconfirmed save is not rewritten as success by navigation or newer editing', () => {
  clearReportDrafts(); const report = {};
  registerReportDraft(report, 'Earlier saved wording', {saved: true});
  trackReportEdits(report, 'New human wording');
  markReportSaving(report); markReportSaveFailed(report, {requestState: {outcome: 'unconfirmed'}});
  registerReportDraft(report, 'New human wording');
  assert.equal(reportSaveState(report).kind, 'unconfirmed');
  assert.match(reportSaveState(report).message, /check My workspace before explicitly trying again/);
  trackReportEditor(report, 'Still newer pending text');
  assert.equal(reportSaveState(report).kind, 'unconfirmed');
  assert.match(reportSaveState(report).message, /waiting to be applied/);
  assert.equal(hasUnsavedReportDrafts(), true);
  markReportSaving(report);
  assert.equal(reportSaveState(report).kind, 'saving');
});

test('prepared partial content survives navigation until its exact report is explicitly saved', () => {
  clearReportDrafts();
  const report = {incomplete: true, finish_reason: 'length', original_input: 'Retained source',
    document_markdown: 'Useful partial finding'};
  const original = structuredClone(report);
  registerReportDraft(report, report.document_markdown);
  registerReportDraft(report, report.document_markdown); // Restored session view.
  trackReportEditor(report, 'Pending clarification'); trackReportEditor(report, '', false);
  assert.equal(hasUnsavedReportDrafts(), true);
  assert.equal(unsavedReportDrafts()[0].report, report);
  assert.match(reportSaveState(report).message, /not saved/);
  const savedCopy = structuredClone(report);
  registerReportDraft(savedCopy, savedCopy.document_markdown, {saved: true});
  assert.equal(reportSaveState(savedCopy).kind, 'saved');
  assert.equal(unsavedReportDrafts().length, 1); // Fetched copy never clears the prepared object.
  markReportSaved(report, report.document_markdown);
  assert.equal(hasUnsavedReportDrafts(), false);
  assert.deepEqual(report, original);
});

test('observed not-sent and rejected saves stay distinct from unknown writes', () => {
  for (const outcome of ['not-sent', 'rejected', 'unconfirmed', 'unrecognised']) {
    clearReportDrafts(); const report = {};
    registerReportDraft(report, 'Retained draft'); markReportSaving(report);
    markReportSaveFailed(report, {requestState: {outcome}});
    assert.equal(reportSaveState(report).kind, outcome === 'unrecognised' ? 'unconfirmed' : outcome);
    assert.equal(hasUnsavedReportDrafts(), true);
    if (outcome === 'not-sent') assert.match(reportSaveState(report).message, /was not sent/);
    if (outcome === 'rejected') assert.match(reportSaveState(report).message, /rejected this save/);
    assert.equal(unsavedReportDrafts()[0].content, 'Retained draft');
  }
});

test('an uncertain redundant save remains protected without claiming the earlier copy disappeared', () => {
  clearReportDrafts(); const report = {};
  registerReportDraft(report, 'Known saved wording', {saved: true});
  assert.equal(hasUnsavedReportDrafts(), false);
  markReportSaving(report); markReportSaveFailed(report, {requestState: {outcome: 'unconfirmed'}});
  assert.equal(hasUnsavedReportDrafts(), true);
  assert.equal(registerReportDraft(report, 'Known saved wording').saved, true);
  markReportSaved(report, 'Known saved wording');
  assert.equal(hasUnsavedReportDrafts(), false);
});

test('acknowledging an earlier snapshot leaves later applied text and pending forms visible', () => {
  clearReportDrafts(); const report = {};
  registerReportDraft(report, 'Original', {saved: true});
  trackReportEdits(report, 'Submitted wording'); markReportSaving(report);
  trackReportEdits(report, 'Newer wording');
  trackReportForm(report, 'handover-summary', {rows: [{status: 'Unknown'}]});
  markReportSaved(report, 'Submitted wording');
  assert.equal(reportSaveState(report).kind, 'pending');
  assert.match(reportSaveState(report).message, /Applied document edits have not been saved/);
  assert.match(reportSaveState(report).message, /Summary rows have not been applied/);
  clearReportForm(report, 'handover-summary');
  assert.equal(reportSaveState(report).kind, 'pending');
  markReportSaved(report, 'Newer wording');
  assert.equal(reportSaveState(report).kind, 'saved');
});

test('pending editor and form states cannot be cleared by saving only the applied document', () => {
  clearReportDrafts(); const report = {};
  registerReportDraft(report, 'Original', {saved: true});
  trackReportEditor(report, 'Pending text');
  trackReportForm(report, 'handover-summary', {rows: [{status: 'Unknown'}]});
  markReportSaved(report, 'Original');
  assert.equal(reportSaveState(report).kind, 'pending');
  assert.match(reportSaveState(report).message, /Draft text is waiting to be applied/);
  trackReportEditor(report, '', false);
  assert.match(reportSaveState(report).message, /Summary rows/);
  clearReportForm(report, 'handover-summary');
  assert.equal(reportSaveState(report).kind, 'saved');
});

test('retained screening changes need saving even when the displayed document is unchanged', () => {
  clearReportDrafts();
  const report = {markdown: 'Original evidence', document_markdown: 'Same useful letter',
    screening: {checks: []}, incomplete: true, model_review: 'Review kept'};
  registerReportDraft(report, report.document_markdown, {saved: true});
  report.screening.checks.push({status: 'unknown', reason: 'Applicant evidence needed'});
  report.markdown += '\nNew screening record';
  trackReportEdits(report, report.document_markdown);
  assert.equal(reportSaveState(report).kind, 'pending');
  assert.match(reportSaveState(report).message, /retained records have not been saved/);
  assert.equal(hasUnsavedReportDrafts(), true);
  const sent = structuredClone(report); markReportSaving(report);
  report.screening.checks.push({status: 'not_met', reason: 'Later user-entered assessment'});
  trackReportEdits(report, report.document_markdown);
  markReportSaved(report, sent.document_markdown, sent);
  assert.equal(reportSaveState(report).kind, 'pending');
  assert.equal(hasUnsavedReportDrafts(), true);
  assert.equal(report.screening.checks.length, 2);
  markReportSaved(report, report.document_markdown, structuredClone(report));
  assert.equal(reportSaveState(report).kind, 'saved');
  assert.equal(hasUnsavedReportDrafts(), false);
  assert.equal(report.incomplete, true); assert.equal(report.model_review, 'Review kept');
});

test('shared save observations refresh reopened views and prune detached views without undoing acknowledgement', () => {
  clearReportDrafts(); const report = {};
  const state = registerReportDraft(report, 'Prepared');
  const observations = [];
  observeReportSaveState(report, () => false); // A view removed by navigation.
  observeReportSaveState(report, () => { observations.push(reportSaveState(report).kind); });
  markReportSaving(report);
  assert.deepEqual(observations, ['saving']); assert.equal(state.views.size, 1);
  observeReportSaveState(report, () => { throw new Error('Fictional view refresh failure'); });
  const failures = markReportSaved(report, 'Prepared', structuredClone(report));
  assert.equal(failures.length, 1); assert.match(failures[0].message, /view refresh failure/);
  assert.equal(reportSaveState(report).kind, 'saved');
  assert.equal(hasUnsavedReportDrafts(), false);
  assert.deepEqual(observations, ['saving', 'saved']);
});

test('reopening prunes disconnected report views before another save is attempted', () => {
  clearReportDrafts(); const report = {}, state = registerReportDraft(report, 'Prepared');
  let connected = true, staleCalls = 0;
  observeReportSaveState(report, () => { staleCalls++; }, () => connected);
  connected = false;
  observeReportSaveState(report, () => {});
  assert.equal(state.views.size, 1); assert.equal(staleCalls, 0);
  markReportSaving(report); assert.equal(staleCalls, 0);
});
