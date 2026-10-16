import assert from 'node:assert/strict';
import test from 'node:test';
import {registerReportDraft, trackReportEditor, trackReportEdits, trackReportForm,
  reportEditorDraft, reportFormDraft, markReportSaved, markReportSaving,
  markReportSaveFailed, clearReportDrafts, unsavedReportDrafts,
  reportReplacementState, reportReplacementUnchanged} from '../src/sinter/web/report-drafts.js';
import {authorizeReportReplacement, reportReplacementStillAllowed,
  retainReportResult, reportCorrectionPayload, reportPreparationInputKey} from '../src/sinter/web/report-replacement.js';

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

function meetingEntry(notes = 'Alex: No purchase was approved.', number = 1) {
  const original = {id: 'S' + 'a'.repeat(16), sha256: 'b'.repeat(64),
    title: 'Original transcript', kind: 'transcript', url: '', content: notes,
    retrieved_at: '2026-10-16T04:20:27+00:00'};
  return retainReportResult({workflow: 'meeting', sources: [original]},
    {workflow: 'meeting', notes, corrections: []}, number);
}

test('meeting corrections carry only the selected original source metadata and never mutate it', () => {
  const a = meetingEntry(), b = meetingEntry('Sam: Approval is still needed.', 2);
  b.report.sources[0].retrieved_at = '2026-10-16T04:20:28+00:00';
  const before = structuredClone(a);
  const edits = [{segment_id: 'T0001', replacement: 'Reviewed wording'}];
  const requestB = reportCorrectionPayload(b, edits);
  const requestA = reportCorrectionPayload(a, edits);
  assert.equal(requestA.notes, a.payload.notes);
  assert.deepEqual(requestA.transcript_source, {id: a.report.sources[0].id,
    sha256: a.report.sources[0].sha256, retrieved_at: a.report.sources[0].retrieved_at});
  assert.notEqual(requestA.transcript_source.retrieved_at, requestB.transcript_source.retrieved_at);
  assert.equal(Object.hasOwn(requestA.transcript_source, 'content'), false);
  const corrected = retainReportResult(a.report, requestA, 3);
  const form = structuredClone(requestA); delete form.transcript_source;
  assert.equal(corrected.inputKey, reportPreparationInputKey(form));
  assert.equal(corrected.inputKey, JSON.stringify(form));
  assert.deepEqual(corrected.payload.transcript_source, requestA.transcript_source);
  assert.notEqual(corrected.inputKey, reportPreparationInputKey({...form, notes: 'Changed notes'}));
  assert.notEqual(corrected.inputKey, reportPreparationInputKey({...form, corrections: []}));
  edits[0].replacement = 'Changed after capture';
  requestA.transcript_source.retrieved_at = 'Changed returned object';
  assert.equal(requestA.corrections[0].replacement, 'Reviewed wording');
  assert.deepEqual(a, before);
  assert.equal(corrected.payload.transcript_source.retrieved_at,
    before.report.sources[0].retrieved_at);
});

test('missing or inconsistent meeting source records fail without silently recapturing evidence', () => {
  const cases = [
    entry => { delete entry.report.sources; },
    entry => { entry.report.sources = []; },
    entry => { entry.report.sources.push({...entry.report.sources[0]}); },
    entry => { entry.report.sources.push({kind: 'reference_excerpt'}); },
    entry => { entry.payload.notes = 'Changed transcript'; },
    entry => { entry.report.sources[0].title = 'Different source'; },
    entry => { entry.report.sources[0].kind = 'user_note'; },
    entry => { entry.report.sources[0].url = 'https://example.org'; },
    entry => { entry.report.sources[0].id = 'bad identity'; },
    entry => { entry.report.sources[0].sha256 = 'not a hash'; },
    entry => { entry.report.sources[0].retrieved_at = ''; },
  ];
  for (const change of cases) {
    const entry = meetingEntry(); change(entry);
    const before = structuredClone(entry);
    assert.throws(() => reportCorrectionPayload(entry, []), /snapshot is missing or inconsistent/);
    assert.deepEqual(entry, before);
  }
});
