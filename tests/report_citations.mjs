import assert from 'node:assert/strict';
import test from 'node:test';
import {reportCitationReferences, reportCitationMatches, reportCitationMatcher} from '../src/sinter/web/report-citations.js';

test('casebook 24-character and legacy identities resolve to exact original sources', () => {
  const source = 'S' + 'a'.repeat(24), excerpt = 'E' + 'b'.repeat(24);
  const legacy = 'S' + 'c'.repeat(16);
  const references = reportCitationReferences({sources: [{id: source}, {id: legacy}],
    excerpts: [{id: excerpt, source_id: source}],
    question_index: [{matches: [{excerpt_id: 'e123', source_id: legacy}]}]});
  const text = `Related passages: ${excerpt}, ${legacy}. [e123] ${source}`;
  const matches = reportCitationMatches(text, references);
  assert.deepEqual(matches.map(row => [row.id, row.sourceId]),
    [[excerpt, source], [legacy, legacy], ['e123', legacy], [source, source]]);
  for (const row of matches) assert.equal(text.slice(row.index, row.index + row.id.length), row.id);
});

test('unknown identities and excerpt links to absent originals remain plain text', () => {
  const references = reportCitationReferences({sources: [{id: 'S1'}],
    excerpts: [{id: 'E1', source_id: 'missing'}],
    question_index: [{matches: [{excerpt_id: 'e2', source_id: 'missing'}]}]});
  assert.deepEqual(reportCitationMatches('E1 e2 S999', references), []);
  assert.equal(references.has('E1'), false);
});

test('known identity matching escapes punctuation and rejects partial or embedded IDs', () => {
  const references = reportCitationReferences({sources: [{id: 'source.a+1'}, {id: 'S1'}, {id: 'S12'}]});
  const text = 'sourceXa+1 source.a+1 | S12 S1 S123 XS1 S1_suffix S1-extra 文S1 S1文';
  assert.deepEqual(reportCitationMatches(text, references).map(row => row.id), ['source.a+1', 'S12', 'S1']);
});

test('missing and malformed optional reference collections do not create links', () => {
  for (const report of [{}, {sources: {}, excerpts: {}, question_index: {}},
    {sources: [null, {}, {id: ''}], excerpts: [null], question_index: [null]}]) {
    assert.deepEqual(reportCitationMatches('S1', reportCitationReferences(report)), []);
  }
});

test('a compiled report matcher resolves each paragraph independently', () => {
  const matcher = reportCitationMatcher(reportCitationReferences({sources: [{id: 'S1'}]}));
  assert.deepEqual(matcher('S1').map(row => row.index), [0]);
  assert.deepEqual(matcher('See S1, S1.').map(row => row.index), [4, 8]);
  assert.deepEqual(matcher('S1').map(row => row.index), [0]);
});
