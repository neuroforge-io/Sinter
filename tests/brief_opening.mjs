import assert from 'node:assert/strict';
import test from 'node:test';
import {openingParagraphProblem, briefOpeningCopy} from '../src/sinter/web/brief-opening.js';
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

test('model handoff shows the entire raw opening and its different model treatment', () => {
  const opening = 'I am following up on our recorded enquiry. Café e\u0301 🐝.\nNo approval is inferred.';
  const payload = {workflow: 'brief', opening_paragraph: opening,
    title: 'Fictional follow-up', notes: 'Internal review context for explicit model preview.',
    sources: [{title: 'Original source', content: 'Original conditions.', url: 'https://example.invalid'}]};
  const before = structuredClone(payload);
  const context = campaignLetterModelContext(payload);
  assert.ok(context.includes('Opening paragraph entered by you (the model may revise it):\n' + opening));
  assert.equal(context.split(opening).length - 1, 1);
  assert.ok(context.includes(payload.notes) && context.includes(payload.sources[0].content));
  assert.deepEqual(payload, before);
  const long = '🐝'.repeat(1200);
  assert.ok(campaignLetterModelContext({...payload, opening_paragraph: long}).includes(long));
  for (const value of [null, '🐝'.repeat(1201), '\ud800']) {
    assert.throws(() => campaignLetterModelContext({...payload, opening_paragraph: value}), /Opening paragraph/);
  }
  assert.throws(() => campaignLetterModelContext({...payload, workflow: 'meeting'}), /briefing documents only/);
});

test('format change makes the agenda purpose role explicit without rewriting text', () => {
  assert.match(briefOpeningCopy('agenda').label, /Purpose.*agenda/);
  assert.match(briefOpeningCopy('agenda').help, /Review it after changing formats/);
  assert.match(briefOpeningCopy('enquiry').help, /preparing locally/);
});
