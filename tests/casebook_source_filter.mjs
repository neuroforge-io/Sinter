import assert from 'node:assert/strict';
import test from 'node:test';
import {sourceFilterMatches, sourceFilterView, sourceFilterStates} from '../src/sinter/web/casebook-source-filter.js';
import {sourceCountLabel} from '../src/sinter/web/casebook-scope.js';

test('source counts are truthful for none, one and the 300-source capacity', () => {
  assert.equal(sourceCountLabel(0), '0 sources');
  assert.equal(sourceCountLabel(1), '1 source');
  assert.equal(sourceCountLabel(300), '300 sources');
});

const documents = [
  {id: 'S' + '1'.repeat(24), title: 'Same supplied title 🐝', date: '2026-09-01', url: 'https://example.invalid/first', content: 'Only the body contains unicorn.'},
  {id: 'S' + '2'.repeat(24), title: 'Same supplied title 🐝', date: '2026-09-02', url: 'https://example.invalid/second', content: 'Exact second body.'},
  {id: 'S' + '3'.repeat(24), title: 'Governing policy', content: 'Evidence remains local.'},
];

test('metadata matching never searches or evaluates original source bodies', () => {
  assert.equal(sourceFilterMatches(documents[0], 'unicorn'), false);
  const guarded = {...documents[0]};
  Object.defineProperty(guarded, 'content', {get: () => { throw new Error('No body reads'); }});
  assert.equal(sourceFilterMatches(guarded, 'same 🐝 2026-09-01 first'), true);
});

test('same-title sources are distinguishable by supplied date, link and exact reference', () => {
  assert.deepEqual(sourceFilterView(documents, [], {query: 'same supplied'}).visibleIndices, [0, 1]);
  for (const query of ['2026-09-02', 'SECOND', documents[1].id]) {
    assert.deepEqual(sourceFilterView(documents, [], {query}).visibleIndices, [1]);
  }
});

test('filtering retains choices outside the view and counts unavailable selected identities honestly', () => {
  const ids = [documents[0].id, documents[2].id, 'S' + '9'.repeat(24)];
  const before = JSON.stringify({documents, ids});
  assert.deepEqual(sourceFilterView(documents, ids, {query: 'first', selectedOnly: true}), {
    visibleIndices: [0], totalSources: 3, selectedTotal: 3, selectedOutsideView: 2,
  });
  assert.equal(JSON.stringify({documents, ids}), before);
});

test('an explicit empty selection never becomes all sources through selected-only or search clearing', () => {
  assert.deepEqual(sourceFilterView(documents, [], {selectedOnly: true}), {
    visibleIndices: [], totalSources: 3, selectedTotal: 0, selectedOutsideView: 0,
  });
  assert.deepEqual(sourceFilterView(documents, [], {query: ''}).visibleIndices, [0, 1, 2]);
});

test('empty, whitespace and unmatched views do not remove hidden evidence choices', () => {
  const ids = documents.map(row => row.id);
  for (const query of ['', ' \t\n ']) {
    assert.deepEqual(sourceFilterView(documents, ids, {query}).visibleIndices, [0, 1, 2]);
  }
  assert.deepEqual(sourceFilterView(documents, ids, {query: 'not supplied anywhere'}), {
    visibleIndices: [], totalSources: 3, selectedTotal: 3, selectedOutsideView: 3,
  });
  assert.equal(ids.length, 3);
});

test('multi-term filters require all terms in supplied metadata, and do not invent an unknown date', () => {
  assert.equal(sourceFilterMatches(documents[0], 'same second'), false);
  assert.equal(sourceFilterMatches(documents[2], 'unknown'), false);
  assert.equal(sourceFilterMatches({title: 'Unsaved source'}, 'unsaved'), true);
  assert.equal(sourceFilterMatches({title: 'Unsaved source'}, 'S999'), false);
});

test('only explicit selected identities enter selected-only view, with original source ordering preserved', () => {
  const ids = [documents[2].id, documents[0].id];
  assert.deepEqual(sourceFilterView(documents, ids, {selectedOnly: true}).visibleIndices, [0, 2]);
  assert.deepEqual(ids, [documents[2].id, documents[0].id]);
});

test('visually identical NFC and decomposed metadata match without rewriting original text', () => {
  const original = {title: 'Cafe\u0301 access', content: 'Literal e\u0301 body'};
  assert.equal(sourceFilterMatches(original, 'Café'), true);
  assert.equal(sourceFilterMatches({title: 'Café access'}, 'Cafe\u0301'), true);
  assert.equal(original.title, 'Cafe\u0301 access');
  assert.equal(original.content, 'Literal e\u0301 body');
});

test('view state belongs only to exact current anchors and cannot be transplanted to a replaced question', () => {
  const questions = ['First question', 'Second question'];
  const first = {question_index: 0, question: questions[0], query: 'Café', selected_only: true};
  const second = {...first, question_index: 1, question: questions[1], query: 'date'};
  const before = JSON.stringify([first, second]);
  assert.deepEqual(sourceFilterStates(questions, [second, first]), [first, second]);
  assert.deepEqual(sourceFilterStates([...questions].reverse(), [first, second]), []);
  assert.deepEqual(sourceFilterStates(['Replaced question', questions[1]], [first, second]), [second]);
  for (const change of [{question_index: true}, {question_index: -1}, {question_index: 3},
    {question: 'Changed'}, {query: null}, {selected_only: 'yes'}, {extra: true}]) {
    assert.deepEqual(sourceFilterStates(questions, [{...first, ...change}]), []);
  }
  assert.deepEqual(sourceFilterStates(questions, [first, first]), [first]);
  assert.deepEqual(sourceFilterStates(questions, null), []);
  assert.equal(JSON.stringify([first, second]), before);
});
