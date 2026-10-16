import assert from 'node:assert/strict';
import test from 'node:test';
import {openingParagraphProblem, briefOpeningCopy, briefContextCopy,
  enquiryModelDraftProblem} from '../src/sinter/web/brief-opening.js';
import {campaignLetterModelContext} from '../src/sinter/web/campaign-letter.js';

test('opening admission counts Unicode code points without cutting input', () => {
  const boundary = '🐝'.repeat(1200);
  assert.equal(boundary.length, 2400);
  assert.equal(openingParagraphProblem(boundary), '');
  assert.match(openingParagraphProblem(boundary + 'e'), /1,200 characters/);
  assert.equal(openingParagraphProblem('café e\u0301\nSecond line.\tRetained.'), '');
  for (const value of [null, [], true, 'bad\0text', '\ud800', '\udfff']) {
    assert.ok(openingParagraphProblem(value));
  }
});

test('model handoff preserves only the entire title and validated recipient opening', () => {
  const opening = '  I am following up. Café e\u0301 🐝.\r\nNo approval is inferred.\n';
  const payload = {workflow: 'brief', document_type: 'enquiry', opening_paragraph: opening,
    title: '  Fictional follow-up café e\u0301 🐝  ',
    notes: 'PRIVATE NOTES MARKER',
    sources: [{title: 'PRIVATE SOURCE TITLE', content: 'PRIVATE SOURCE BODY', url: 'https://example.invalid/private-source'}],
    recipient: 'RECIPIENT SEPARATE', questions: 'QUESTIONS SEPARATE', signatory: 'SENDER SEPARATE',
    campaign_link: {internal: 'PRIVATE CAMPAIGN LINK'}, profile: {internal: 'PRIVATE PROFILE'}};
  const before = structuredClone(payload);
  const context = campaignLetterModelContext(payload);
  assert.equal(context, payload.title + '\n\nOpening paragraph entered by you (the model may revise it):\n' + opening);
  assert.equal(context.split(opening).length - 1, 1);
  assert.deepEqual(payload, before);
  const long = '🐝'.repeat(1200);
  assert.ok(campaignLetterModelContext({...payload, opening_paragraph: long}).endsWith(long));
  for (const value of [null, '🐝'.repeat(1201), '\ud800']) {
    assert.throws(() => campaignLetterModelContext({...payload, opening_paragraph: value}), /Opening paragraph/);
  }
});

test('letter handoff does not inspect excluded notes, evidence or internal metadata', () => {
  const payload = {workflow: 'brief', document_type: 'enquiry', title: 'Local enquiry'};
  for (const key of ['notes', 'sources', 'profile', 'campaign_link', 'speaker_map', 'corrections']) {
    Object.defineProperty(payload, key, {get() { throw new Error('Excluded field read: ' + key); }});
  }
  assert.equal(campaignLetterModelContext(payload), 'Local enquiry');
});

test('model letter eligibility rejects other workflows and formats without altering input', () => {
  assert.equal(enquiryModelDraftProblem({}), '');
  assert.equal(enquiryModelDraftProblem({workflow: 'brief', document_type: 'enquiry'}), '');
  const valid = {workflow: 'brief', document_type: 'enquiry', title: 'Original local title',
    opening_paragraph: 'Original opening.\r\nNext line.', notes: 'PRIVATE NOTE',
    sources: [{title: 'Original source', content: 'Unchanged evidence.'}]};
  for (const change of [
    ...['research', 'grants', 'meeting', '', null].map(workflow => ({workflow})),
    ...['briefing', 'agenda', 'unknown', '', null, false, []].map(document_type => ({document_type})),
  ]) {
    const payload = {...valid, ...change};
    const before = structuredClone(payload);
    const problem = enquiryModelDraftProblem(payload);
    assert.match(problem, /enquiry letters.*local inputs are unchanged/i);
    assert.throws(() => campaignLetterModelContext(payload), {message: problem});
    assert.deepEqual(payload, before);
  }
});

test('context copy distinguishes enquiry evidence from quoted briefing and agenda background', () => {
  assert.match(briefContextCopy('enquiry').label, /Internal notes/);
  assert.match(briefContextCopy('enquiry').help, /do not appear in its body/);
  for (const format of ['briefing', 'agenda']) {
    assert.match(briefContextCopy(format).label, /Background/);
    assert.match(briefContextCopy(format).help, /may appear as quoted background/);
    assert.match(briefContextCopy(format).help, /Changing formats keeps your original text/);
  }
  for (const format of ['enquiry', 'briefing', 'agenda']) {
    const copy = briefContextCopy(format, true);
    assert.equal(copy.label, 'Internal notes and evidence context');
    assert.match(copy.help, /evidence pack in every format/);
  }
});

test('format change makes the agenda purpose role explicit without rewriting text', () => {
  assert.match(briefOpeningCopy('agenda').label, /Purpose.*agenda/);
  assert.match(briefOpeningCopy('agenda').help, /Review it after changing formats/);
  assert.match(briefOpeningCopy('enquiry').help, /preparing locally/);
});
