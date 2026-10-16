import assert from 'node:assert/strict';
import test from 'node:test';
import {registerReportDraft, trackReportEditor, trackReportEdits, trackReportForm,
  reportEditorDraft, reportFormDraft, markReportSaved, markReportSaving,
  markReportSaveFailed, clearReportDrafts, unsavedReportDrafts,
  reportReplacementState, reportReplacementUnchanged} from '../src/sinter/web/report-drafts.js';
import {authorizeReportReplacement, reportReplacementStillAllowed,
  retainReportResult, reportCorrectionPayload} from '../src/sinter/web/report-replacement.js';

function setup(saved = false) {
  clearReportDrafts();
  const report = {title: 'Fictional enquiry', document_markdown: 'Original',
    input_snapshot: {opening_paragraph: 'First opening'}, sources: [{id: 'source-a', content: 'Eligibility unconfirmed.'}]};
  registerReportDraft(report, 'Original', {saved});
  return report;
}
const options = confirm => ({confirm, isActive: () => true});

test('untouched generated and explicitly saved reports need no extra decision', async () => {
  for (const saved of [false, true]) {
    const report = setup(saved), before = structuredClone(report);
    const authorization = await authorizeReportReplacement(report, options(() => assert.fail('Unexpected decision')));
    assert.equal(reportReplacementStillAllowed(report, authorization), true);
    assert.deepEqual(report, before);
  }
});

test('pending editor, applied edits, forms and retained-record changes all require a decision', async () => {
  for (const edit of [r => trackReportEditor(r, 'Unapplied last keystroke'),
    r => trackReportEdits(r, 'Applied edit'), r => trackReportForm(r, 'summary', {owner: 'Unknown'}),
    r => { r.campaign_link = {revision: 6}; }]) {
    const report = setup(); edit(report); let decisions = 0;
    assert.equal(await authorizeReportReplacement(report, options(() => { decisions++; return false; })), null);
    assert.equal(decisions, 1);
    const authorization = await authorizeReportReplacement(report, options(() => true));
    assert.equal(reportReplacementStillAllowed(report, authorization), true);
  }
});

test('save in progress blocks preparation without opening a decision or replaying a save', async () => {
  const report = setup(); markReportSaving(report);
  await assert.rejects(authorizeReportReplacement(report, options(() => assert.fail('No decision during save'))), /Wait for this document’s save/);
  assert.equal(reportReplacementState(report).saving, true);
});

test('not-sent, rejected and uncertain saves require a decision without changing their outcome', async () => {
  for (const outcome of ['not-sent', 'rejected', 'unconfirmed']) {
    const report = setup(); markReportSaveFailed(report, {requestState: {outcome}});
    const before = reportReplacementState(report);
    assert.equal(await authorizeReportReplacement(report, options(() => false)), null);
    assert.equal(reportReplacementUnchanged(report, before), true);
  }
});

test('approval is invalidated by edits, forms, retained metadata or saves during preparation', async () => {
  for (const change of [r => trackReportEditor(r, 'Later pending edit'),
    r => trackReportEdits(r, 'Later applied edit'), r => trackReportForm(r, 'summary', {date: 'Unconfirmed'}),
    r => { r.campaign_link = {revision: 7}; }, r => markReportSaving(r),
    r => markReportSaved(r, 'Original')]) {
    const report = setup();
    const authorization = await authorizeReportReplacement(report, options(() => true));
    change(report);
    assert.equal(reportReplacementStillAllowed(report, authorization), false);
  }
});

test('a decision cannot authorise an edit made while it was open', async () => {
  const report = setup(); trackReportEditor(report, 'Pending');
  await assert.rejects(authorizeReportReplacement(report, options(() => {
    trackReportEditor(report, 'Pending plus another keystroke'); return true;
  })), /changed while the decision was open/);
  assert.equal(reportEditorDraft(report).text, 'Pending plus another keystroke');
});

test('detached or cancelled decisions do not grant replacement', async () => {
  const report = setup(); trackReportEditor(report, 'Keep me'); let active = true;
  assert.equal(await authorizeReportReplacement(report, {isActive: () => active,
    confirm: () => { active = false; return true; }}), null);
  assert.equal(await authorizeReportReplacement(report, {isActive: () => false,
    confirm: () => assert.fail('Detached view must not open a decision')}), null);
});

test('opaque tokens remain stable on inspection but distinguish reports with identical names', async () => {
  const report = setup(), a = reportReplacementState(report), b = reportReplacementState(report);
  assert.equal(a.token, b.token); assert.equal(Object.isFrozen(a.token), true);
  const authorization = await authorizeReportReplacement(report, options(() => true));
  const other = structuredClone(report); registerReportDraft(other, 'Original');
  assert.equal(reportReplacementStillAllowed(other, authorization), false);
  assert.equal(reportReplacementStillAllowed(report, authorization), true);
});

test('retaining a completed result never rewrites previous inputs, evidence, forms or edits', async () => {
  const report = setup();
  trackReportEditor(report, 'Unapplied historical text'); trackReportForm(report, 'summary', {owner: 'Unknown'});
  const original = structuredClone(report);
  const authorization = await authorizeReportReplacement(report, options(() => true));
  const newReport = {...structuredClone(report), document_markdown: 'New result', input_snapshot: {opening_paragraph: 'Second opening'}};
  registerReportDraft(newReport, 'New result');
  assert.equal(reportReplacementStillAllowed(report, authorization), true);
  assert.deepEqual(report, original);
  assert.equal(reportEditorDraft(report).text, 'Unapplied historical text');
  assert.deepEqual(reportFormDraft(report, 'summary'), {owner: 'Unknown'});
  assert.deepEqual(unsavedReportDrafts().map(s => s.report), [report, newReport]);
  registerReportDraft(report, 'Original');
  assert.equal(reportEditorDraft(report).text, 'Unapplied historical text');
});

test('A to B to A corrections use A’s own captured input, not the latest attempt', () => {
  const report = setup();
  const inputA = {notes: 'Original transcript A', sources: [{id: 'a', content: 'A'}], corrections: []};
  const a = retainReportResult(report, inputA, 1);
  const b = retainReportResult({}, {notes: 'Later transcript B', sources: [{id: 'b', content: 'B'}]}, 2);
  inputA.notes = 'Changed form'; inputA.sources[0].content = 'Changed form source';
  const corrections = [{segment: 1, text: 'Explicit correction to A'}];
  const request = reportCorrectionPayload(a, corrections);
  corrections[0].text = 'Changed after decision';
  assert.equal(request.notes, 'Original transcript A');
  assert.deepEqual(request.sources, [{id: 'a', content: 'A'}]);
  assert.equal(request.corrections[0].text, 'Explicit correction to A');
  assert.equal(JSON.parse(a.inputKey).notes, 'Original transcript A');
  assert.equal(JSON.parse(b.inputKey).notes, 'Later transcript B');
  assert.deepEqual(a.payload.corrections, []);
});
